import os
import json
import asyncio
from datetime import datetime

from dotenv import load_dotenv
from playwright.async_api import async_playwright


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

BASE_URL = "https://propfinder.app"

WNBA_URLS = {
    "volume_trends": (
        f"{BASE_URL}/wnba/cheatsheets/volume-trends"
    ),
    "injury_splits": (
        f"{BASE_URL}/wnba/cheatsheets/injury-splits"
    ),
    "odds_discrepancies": (
        f"{BASE_URL}/wnba/cheatsheets/odds-discrepancies"
    ),
}


# ============================================================
# HELPERS
# ============================================================

def today_string():
    return datetime.now().strftime("%Y-%m-%d")


def clean_text(text):
    if text is None:
        return ""

    return (
        text
        .replace("\xa0", " ")
        .strip()
    )


async def save_json(filename, data):
    os.makedirs("logs", exist_ok=True)

    path = os.path.join(
        "logs",
        filename,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"JSON saved: {path}")


async def take_screenshot(page, filename):
    os.makedirs("logs", exist_ok=True)

    path = os.path.join(
        "logs",
        filename,
    )

    await page.screenshot(
        path=path,
        full_page=True,
    )

    print(f"Screenshot saved: {path}")


# ============================================================
# LOGIN
# ============================================================

async def login(page):

    print("\n" + "=" * 70)
    print("LOGGING INTO PROPFINDER")
    print("=" * 70)

    await page.goto(
        f"{BASE_URL}/login",
        wait_until="domcontentloaded",
        timeout=60000,
    )

    await page.wait_for_timeout(3000)

    email = os.getenv(
        "PROPFINDER_EMAIL"
    )

    password = os.getenv(
        "PROPFINDER_PASSWORD"
    )

    if not email or not password:
        raise RuntimeError(
            "Missing PROPFINDER_EMAIL or "
            "PROPFINDER_PASSWORD in .env"
        )

    await page.get_by_placeholder(
        "your@email.com"
    ).fill(email)

    password_field = (
        page.get_by_placeholder(
            "••••••"
        )
    )

    await password_field.fill(password)

    await password_field.press(
        "Enter"
    )

    try:
        await page.wait_for_url(
            lambda url: (
                "/login" not in url
            ),
            timeout=30000,
        )

    except Exception:
        print(
            "Login redirect took longer "
            "than expected."
        )

    await page.wait_for_timeout(
        3000
    )

    print("Logged in.")
    print(
        "Current URL:",
        page.url,
    )


# ============================================================
# PAGE DIAGNOSTICS
# ============================================================

async def print_comboboxes(page):

    print(
        "\n--- COMBOBOXES ---"
    )

    comboboxes = page.locator(
        '[role="combobox"]'
    )

    count = (
        await comboboxes.count()
    )

    print(
        f"Combobox count: {count}"
    )

    for i in range(count):

        combo = comboboxes.nth(i)

        try:
            text = clean_text(
                await combo.inner_text()
            )

            print(
                f"Combobox #{i + 1}: "
                f"{repr(text)}"
            )

        except Exception as e:

            print(
                f"Combobox #{i + 1}: "
                f"could not read: {e}"
            )


async def print_buttons(page):

    print(
        "\n--- BUTTONS ---"
    )

    buttons = page.locator(
        "button"
    )

    count = (
        await buttons.count()
    )

    print(
        f"Button count: {count}"
    )

    for i in range(
        min(count, 40)
    ):

        button = buttons.nth(i)

        try:

            if not await button.is_visible():
                continue

            text = clean_text(
                await button.inner_text()
            )

            if text:
                print(
                    f"Button #{i + 1}: "
                    f"{repr(text)}"
                )

        except Exception:
            pass


async def print_headers(page):

    print(
        "\n--- DATA HEADERS ---"
    )

    selectors = [
        "th",
        ".MuiDataGrid-columnHeader",
        '[role="columnheader"]',
    ]

    found = set()

    for selector in selectors:

        items = page.locator(
            selector
        )

        count = (
            await items.count()
        )

        for i in range(count):

            try:

                item = items.nth(i)

                if not await item.is_visible():
                    continue

                text = clean_text(
                    await item.inner_text()
                )

                if (
                    text
                    and text not in found
                ):
                    found.add(text)
                    print(text)

            except Exception:
                pass


# ============================================================
# HTML TABLE EXTRACTION
# ============================================================

async def extract_html_table(page):

    rows = page.locator(
        "table tr"
    )

    count = (
        await rows.count()
    )

    output = []

    for i in range(count):

        try:

            row = rows.nth(i)

            cells = row.locator(
                "th, td"
            )

            cell_count = (
                await cells.count()
            )

            values = []

            if cell_count > 0:

                for j in range(
                    cell_count
                ):

                    try:

                        value = clean_text(
                            await cells
                            .nth(j)
                            .inner_text()
                        )

                        values.append(
                            value
                        )

                    except Exception:
                        values.append("")

            else:

                text = clean_text(
                    await row.inner_text()
                )

                if text:
                    values.append(text)

            if values:
                output.append(
                    values
                )

        except Exception:
            continue

    return output


# ============================================================
# MATERIAL UI DATAGRID EXTRACTION
# ============================================================

async def extract_datagrid(page):

    rows_seen = {}

    scroller = page.locator(
        ".MuiDataGrid-virtualScroller"
    )

    row_locator = page.locator(
        ".MuiDataGrid-row"
    )

    # --------------------------------------------------------
    # If no DataGrid exists, return empty
    # --------------------------------------------------------

    if await row_locator.count() == 0:
        return []

    # --------------------------------------------------------
    # Collect currently rendered rows
    # --------------------------------------------------------

    async def collect_visible_rows():

        count = (
            await row_locator.count()
        )

        for i in range(count):

            row = row_locator.nth(i)

            try:

                cells = row.locator(
                    ".MuiDataGrid-cell"
                )

                cell_count = (
                    await cells.count()
                )

                values = []

                for j in range(
                    cell_count
                ):

                    try:

                        value = clean_text(
                            await cells
                            .nth(j)
                            .inner_text()
                        )

                        values.append(
                            value
                        )

                    except Exception:
                        values.append("")

                if values:

                    key = "|".join(
                        values
                    )

                    rows_seen[key] = (
                        values
                    )

            except Exception:
                continue

    await collect_visible_rows()

    # --------------------------------------------------------
    # Scroll through virtualized grid
    # --------------------------------------------------------

    if await scroller.count() > 0:

        for _ in range(20):

            try:

                old_count = len(
                    rows_seen
                )

                await scroller.evaluate(
                    """
                    element => {
                        element.scrollTop =
                            element.scrollTop + 500;
                    }
                    """
                )

                await page.wait_for_timeout(
                    600
                )

                await collect_visible_rows()

                new_count = len(
                    rows_seen
                )

                # Continue scrolling even if one
                # pass did not reveal anything.
                if new_count == old_count:
                    await page.wait_for_timeout(
                        300
                    )

            except Exception:
                break

    return list(
        rows_seen.values()
    )


# ============================================================
# EXTRACT ANY PAGE DATA
# ============================================================

async def extract_page_data(
    page,
    label,
    preview_rows=8,
):

    print(
        "\n" + "-" * 70
    )

    print(
        f"EXTRACTING: {label}"
    )

    print(
        "-" * 70
    )

    html_rows = (
        await extract_html_table(
            page
        )
    )

    grid_rows = (
        await extract_datagrid(
            page
        )
    )

    print(
        f"HTML table rows: "
        f"{len(html_rows)}"
    )

    print(
        f"DataGrid rows: "
        f"{len(grid_rows)}"
    )

    # --------------------------------------------------------
    # Print DataGrid preview first
    # --------------------------------------------------------

    if grid_rows:

        print(
            "\nFirst DataGrid rows:"
        )

        for row in grid_rows[
            :preview_rows
        ]:
            print(row)

    # --------------------------------------------------------
    # Otherwise print HTML table
    # --------------------------------------------------------

    elif html_rows:

        print(
            "\nFirst HTML table rows:"
        )

        for row in html_rows[
            :preview_rows
        ]:
            print(row)

    else:

        print(
            "\nWARNING: No structured "
            "table rows detected."
        )

        try:

            body = clean_text(
                await page.locator(
                    "body"
                ).inner_text()
            )

            print(
                "\nPage text sample:"
            )

            print(
                body[:5000]
            )

        except Exception:
            pass

    return {
        "label": label,
        "url": page.url,
        "html_rows": html_rows,
        "grid_rows": grid_rows,
    }


# ============================================================
# FIND VISIBLE TEXT
# ============================================================

async def click_visible_exact_text(
    page,
    text,
):

    matches = page.get_by_text(
        text,
        exact=True,
    )

    count = (
        await matches.count()
    )

    for i in range(count):

        item = matches.nth(i)

        try:

            if await item.is_visible():

                await item.click()

                return True

        except Exception:
            continue

    return False


# ============================================================
# VOLUME TRENDS WINDOW SELECTION
# ============================================================

async def select_volume_window(
    page,
    window_name,
):

    print(
        f"\nTrying to select "
        f"{window_name}..."
    )

    # --------------------------------------------------------
    # First inspect comboboxes
    # --------------------------------------------------------

    comboboxes = page.locator(
        '[role="combobox"]'
    )

    combo_count = (
        await comboboxes.count()
    )

    target_combo = None

    for i in range(
        combo_count
    ):

        combo = (
            comboboxes.nth(i)
        )

        try:

            text = clean_text(
                await combo.inner_text()
            )

            upper_text = (
                text.upper()
            )

            # Likely Compare dropdown.
            if any(
                value in upper_text
                for value in [
                    "L3",
                    "L5",
                    "L10",
                    "L15",
                ]
            ):

                target_combo = combo
                break

        except Exception:
            continue

    # --------------------------------------------------------
    # If we found the compare combobox, open it
    # --------------------------------------------------------

    if target_combo is not None:

        try:

            print(
                "Opening probable "
                "Compare dropdown..."
            )

            await target_combo.click()

            await page.wait_for_timeout(
                1000
            )

            clicked = (
                await click_visible_exact_text(
                    page,
                    window_name,
                )
            )

            if clicked:

                print(
                    f"Selected "
                    f"{window_name}."
                )

                await page.wait_for_timeout(
                    4000
                )

                return True

        except Exception as e:

            print(
                "Compare combobox attempt "
                f"failed: {e}"
            )

    # --------------------------------------------------------
    # Fallback:
    # Try any visible exact text match
    # --------------------------------------------------------

    clicked = (
        await click_visible_exact_text(
            page,
            window_name,
        )
    )

    if clicked:

        print(
            f"Clicked visible "
            f"{window_name}."
        )

        await page.wait_for_timeout(
            4000
        )

        return True

    # --------------------------------------------------------
    # Another fallback:
    # Look through buttons
    # --------------------------------------------------------

    buttons = page.locator(
        "button"
    )

    button_count = (
        await buttons.count()
    )

    for i in range(
        button_count
    ):

        button = buttons.nth(i)

        try:

            if not await button.is_visible():
                continue

            text = clean_text(
                await button.inner_text()
            )

            if text == window_name:

                await button.click()

                await page.wait_for_timeout(
                    4000
                )

                print(
                    f"Selected "
                    f"{window_name} "
                    "through button."
                )

                return True

        except Exception:
            continue

    print(
        f"Could not automatically "
        f"select {window_name}."
    )

    return False


# ============================================================
# VOLUME TRENDS
# ============================================================

async def test_volume_trends(
    page,
    url,
):

    print(
        "\n" + "=" * 70
    )

    print(
        "TESTING: WNBA VOLUME TRENDS"
    )

    print(url)

    print(
        "=" * 70
    )

    await page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    await page.wait_for_timeout(
        10000
    )

    print(
        "Page title:",
        await page.title(),
    )

    print(
        "Final URL:",
        page.url,
    )

    await print_comboboxes(
        page
    )

    await print_buttons(
        page
    )

    await print_headers(
        page
    )

    results = {}

    # --------------------------------------------------------
    # Capture default state
    # --------------------------------------------------------

    print(
        "\nCapturing default "
        "Volume Trends state..."
    )

    default_data = (
        await extract_page_data(
            page,
            "volume_trends_default",
        )
    )

    results[
        "default"
    ] = default_data

    await take_screenshot(
        page,
        "wnba_volume_trends_default.png",
    )

    # --------------------------------------------------------
    # Test each comparison window
    # --------------------------------------------------------

    windows = [
        "L3",
        "L5",
        "L10",
        "L15",
    ]

    for window in windows:

        print(
            "\n" + "*" * 70
        )

        print(
            f"VOLUME WINDOW: {window}"
        )

        print(
            "*" * 70
        )

        selected = (
            await select_volume_window(
                page,
                window,
            )
        )

        if not selected:

            results[
                window
            ] = {
                "selected": False,
                "rows": [],
            }

            continue

        await print_comboboxes(
            page
        )

        data = (
            await extract_page_data(
                page,
                f"volume_trends_{window}",
            )
        )

        data[
            "selected"
        ] = True

        results[
            window
        ] = data

        await take_screenshot(
            page,
            (
                "wnba_volume_trends_"
                f"{window.lower()}.png"
            ),
        )

    await save_json(
        (
            f"{today_string()}_"
            "wnba_volume_trends_test.json"
        ),
        results,
    )

    print(
        "\nVOLUME TRENDS TEST COMPLETE"
    )


# ============================================================
# INJURY SPLITS
# ============================================================

async def test_injury_splits(
    page,
    url,
):

    print(
        "\n" + "=" * 70
    )

    print(
        "TESTING: WNBA INJURY SPLITS"
    )

    print(url)

    print(
        "=" * 70
    )

    await page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    await page.wait_for_timeout(
        10000
    )

    print(
        "Page title:",
        await page.title(),
    )

    print(
        "Final URL:",
        page.url,
    )

    await print_comboboxes(
        page
    )

    await print_headers(
        page
    )

    data = (
        await extract_page_data(
            page,
            "injury_splits",
            preview_rows=12,
        )
    )

    # --------------------------------------------------------
    # Print page sample to help us identify
    # Quick View / Team View controls and
    # any sample-size labels.
    # --------------------------------------------------------

    try:

        body = clean_text(
            await page.locator(
                "body"
            ).inner_text()
        )

        print(
            "\n--- INJURY SPLITS "
            "PAGE TEXT SAMPLE ---"
        )

        print(
            body[:7000]
        )

    except Exception:
        pass

    await take_screenshot(
        page,
        "wnba_injury_splits.png",
    )

    await save_json(
        (
            f"{today_string()}_"
            "wnba_injury_splits_test.json"
        ),
        data,
    )

    print(
        "\nINJURY SPLITS TEST COMPLETE"
    )


# ============================================================
# ODDS DISCREPANCIES
# ============================================================

async def test_odds_discrepancies(
    page,
    url,
):

    print(
        "\n" + "=" * 70
    )

    print(
        "TESTING: WNBA ODDS DISCREPANCIES"
    )

    print(url)

    print(
        "=" * 70
    )

    await page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    await page.wait_for_timeout(
        10000
    )

    print(
        "Page title:",
        await page.title(),
    )

    print(
        "Final URL:",
        page.url,
    )

    await print_comboboxes(
        page
    )

    await print_headers(
        page
    )

    data = (
        await extract_page_data(
            page,
            "odds_discrepancies",
            preview_rows=12,
        )
    )

    # --------------------------------------------------------
    # Inspect images because sportsbook names
    # may be represented only by logos/icons.
    # --------------------------------------------------------

    print(
        "\n--- IMAGE / SPORTSBOOK "
        "DIAGNOSTIC ---"
    )

    images = page.locator(
        "img"
    )

    image_count = (
        await images.count()
    )

    print(
        f"Images found: "
        f"{image_count}"
    )

    image_data = []

    for i in range(
        min(image_count, 100)
    ):

        image = images.nth(i)

        try:

            src = (
                await image.get_attribute(
                    "src"
                )
            )

            alt = (
                await image.get_attribute(
                    "alt"
                )
            )

            title = (
                await image.get_attribute(
                    "title"
                )
            )

            record = {
                "src": src,
                "alt": alt,
                "title": title,
            }

            image_data.append(
                record
            )

            if alt or title:

                print(
                    f"Image #{i + 1}: "
                    f"alt={repr(alt)}, "
                    f"title={repr(title)}"
                )

        except Exception:
            continue

    data[
        "images"
    ] = image_data

    # --------------------------------------------------------
    # Inspect page text too
    # --------------------------------------------------------

    try:

        body = clean_text(
            await page.locator(
                "body"
            ).inner_text()
        )

        print(
            "\n--- ODDS PAGE "
            "TEXT SAMPLE ---"
        )

        print(
            body[:7000]
        )

    except Exception:
        pass

    await take_screenshot(
        page,
        "wnba_odds_discrepancies.png",
    )

    await save_json(
        (
            f"{today_string()}_"
            "wnba_odds_discrepancies_test.json"
        ),
        data,
    )

    print(
        "\nODDS DISCREPANCIES "
        "TEST COMPLETE"
    )


# ============================================================
# RUN
# ============================================================

async def run():

    os.makedirs(
        "logs",
        exist_ok=True,
    )

    async with async_playwright() as p:

        browser = (
            await p.chromium.launch(
                headless=False
            )
        )

        context = (
            await browser.new_context(
                viewport={
                    "width": 1600,
                    "height": 1000,
                }
            )
        )

        page = (
            await context.new_page()
        )

        try:

            # ------------------------------------------------
            # LOGIN ONCE
            # ------------------------------------------------

            await login(
                page
            )

            # ------------------------------------------------
            # 1. VOLUME TRENDS
            # ------------------------------------------------

            await test_volume_trends(
                page,
                WNBA_URLS[
                    "volume_trends"
                ],
            )

            # ------------------------------------------------
            # 2. INJURY SPLITS
            # ------------------------------------------------

            await test_injury_splits(
                page,
                WNBA_URLS[
                    "injury_splits"
                ],
            )

            # ------------------------------------------------
            # 3. ODDS DISCREPANCIES
            # ------------------------------------------------

            await test_odds_discrepancies(
                page,
                WNBA_URLS[
                    "odds_discrepancies"
                ],
            )

            print(
                "\n" + "=" * 70
            )

            print(
                "ALL THREE WNBA TESTS COMPLETE"
            )

            print(
                "=" * 70
            )

        except Exception as e:

            print(
                "\nERROR:"
            )

            print(
                type(e).__name__
            )

            print(
                str(e)
            )

            try:

                await take_screenshot(
                    page,
                    "wnba_new_sources_error.png",
                )

            except Exception:
                pass

        finally:

            await browser.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    asyncio.run(run())