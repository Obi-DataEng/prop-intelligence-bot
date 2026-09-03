import asyncio
import csv
import time
import json
import os
import re
from datetime import datetime

from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://propfinder.app"

MLB_URLS = {
    "hr_matchups": f"{BASE_URL}/mlb/cheatsheets",
    "exit_velo": f"{BASE_URL}/mlb/cheatsheets/exit-velo",
    "pitcher_summary": f"{BASE_URL}/mlb/cheatsheets/pitcher-summary",
    "park_factors": f"{BASE_URL}/mlb/cheatsheets/park-factors",
    "weather": f"{BASE_URL}/mlb/cheatsheets/ballpark-weather",
    "projections": f"{BASE_URL}/projections/mlb",
}

NBA_URLS = {
    "nba_player_stats": f"{BASE_URL}/nba/cheatsheets/player-stats-summary",
    "nba_team_stats": f"{BASE_URL}/nba/cheatsheets/team-stats",
    "nba_def_matchups": f"{BASE_URL}/nba/cheatsheets/defensive-matchups",
    "nba_hit_rate": f"{BASE_URL}/nba/cheatsheets/hit-rate-matrix",
    "nba_injury_reports": f"{BASE_URL}/nba/cheatsheets/injury-reports",
    "nba_lineups": f"{BASE_URL}/nba/cheatsheets/lineups",
    "nba_research": f"{BASE_URL}/nba",
}

WNBA_URLS = {
    "wnba_research": f"{BASE_URL}/wnba",
    "wnba_player_stats": f"{BASE_URL}/wnba/cheatsheets/player-stats-summary",
    "wnba_team_stats": f"{BASE_URL}/wnba/cheatsheets/team-stats",
    "wnba_hit_rate": f"{BASE_URL}/wnba/cheatsheets/hit-rate-matrix",
    "wnba_injury_reports": f"{BASE_URL}/wnba/cheatsheets/injury-reports",
    "wnba_volume_trends": f"{BASE_URL}/wnba/cheatsheets/volume-trends",
    "wnba_injury_splits": f"{BASE_URL}/wnba/cheatsheets/injury-splits",
    "wnba_odds_discrepancies": f"{BASE_URL}/wnba/cheatsheets/odds-discrepancies",
}

CFB_URLS = {
    "cfb_props": f"{BASE_URL}/cfb",
    "cfb_games": f"{BASE_URL}/cfb/games",
    "cfb_power_ratings": f"{BASE_URL}/cfb/power-ratings",
}

CFB_PAGE_LABELS = {
    "cfb_games": ("Games & Projections", "Games and Projections"),
    "cfb_power_ratings": ("Power Ratings",),
}

NFL_URLS = {
    "nfl_props": f"{BASE_URL}/nfl",
    "nfl_games": f"{BASE_URL}/nfl/games",
    "nfl_weather": f"{BASE_URL}/nfl/weather",
    "nfl_home_field_advantage": f"{BASE_URL}/nfl/home-field-advantage",
    "nfl_odds_discrepancies": (
        f"{BASE_URL}/nfl/cheatsheets/odds-discrepancies"
    ),
}

NRFI_URL = f"{BASE_URL}/nrfi"


# ─────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────

def scrape_date_string():
    return datetime.now().strftime("%Y-%m-%d")


def clean_text(value):
    if value is None:
        return ""
    return value.replace("\xa0", " ").strip()


def save_json(scrape_date, name, data):
    os.makedirs("logs", exist_ok=True)
    filepath = f"logs/{scrape_date}_{name}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"   💾 Saved {filepath}")


async def login(page):
    print("🔐 Logging into PropFinder...")

    await page.goto(
        f"{BASE_URL}/login",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    await page.wait_for_timeout(3000)

    email = os.getenv("PROPFINDER_EMAIL")
    password = os.getenv("PROPFINDER_PASSWORD")

    if not email or not password:
        raise RuntimeError(
            "Missing PROPFINDER_EMAIL or PROPFINDER_PASSWORD in .env"
        )

    await page.get_by_placeholder("your@email.com").fill(email)

    password_field = page.get_by_placeholder("••••••")
    await password_field.fill(password)
    await password_field.press("Enter")

    try:
        await page.wait_for_url(
            lambda url: "/login" not in url,
            timeout=30000,
        )
    except Exception:
        print("   ⚠️ Login redirect took longer than expected")

    await page.wait_for_timeout(3000)

    if "/login" in page.url:
        raise RuntimeError(
            "Still on PropFinder login page. Check PROPFINDER_EMAIL and PROPFINDER_PASSWORD."
        )

    print(f"✅ Logged in — {page.url}")


async def navigate(page, url, wait_ms=5000):
    try:
        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000,
        )
    except Exception:
        print("   ⚠️ First navigation failed, retrying...")
        await page.wait_for_timeout(2500)
        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

    await page.wait_for_timeout(wait_ms)


async def extract_html_table(page):
    rows = page.locator("table tr")
    output = []

    for i in range(await rows.count()):
        row = rows.nth(i)
        cells = row.locator("th, td")
        values = []

        if await cells.count() > 0:
            for j in range(await cells.count()):
                try:
                    values.append(
                        clean_text(await cells.nth(j).inner_text())
                    )
                except Exception:
                    values.append("")
        else:
            try:
                text = clean_text(await row.inner_text())
                if text:
                    values.append(text)
            except Exception:
                pass

        if values:
            output.append(values)

    return output


async def extract_datagrid(page, max_scrolls=40, step=500):
    """
    Collect rows from MUI's virtualized DataGrid by scrolling its internal
    virtual scroller and deduplicating rendered rows.
    """
    row_locator = page.locator(".MuiDataGrid-row")
    scroller = page.locator(".MuiDataGrid-virtualScroller")

    if await row_locator.count() == 0:
        return []

    rows_seen = {}

    async def collect_visible_rows():
        count = await row_locator.count()

        for i in range(count):
            row = row_locator.nth(i)
            cells = row.locator(".MuiDataGrid-cell")
            values = []

            for j in range(await cells.count()):
                try:
                    values.append(
                        clean_text(await cells.nth(j).inner_text())
                    )
                except Exception:
                    values.append("")

            if values:
                key = "|".join(values)
                rows_seen[key] = values

    await collect_visible_rows()

    if await scroller.count() == 0:
        return list(rows_seen.values())

    no_change = 0

    for _ in range(max_scrolls):
        before = len(rows_seen)

        try:
            result = await scroller.evaluate(
                f"""
                element => {{
                    const previous = element.scrollTop;
                    element.scrollTop = Math.min(
                        element.scrollTop + {step},
                        element.scrollHeight
                    );
                    return {{
                        previous,
                        current: element.scrollTop,
                        height: element.scrollHeight,
                        clientHeight: element.clientHeight
                    }};
                }}
                """
            )
        except Exception:
            break

        await page.wait_for_timeout(500)
        await collect_visible_rows()

        after = len(rows_seen)

        if after == before:
            no_change += 1
        else:
            no_change = 0

        at_bottom = (
            result["current"] + result["clientHeight"]
            >= result["height"] - 5
        )

        if at_bottom and no_change >= 2:
            break

        if no_change >= 6:
            break

    return list(rows_seen.values())


async def extract_headers(page):
    headers = []
    seen = set()

    for selector in [
        "th",
        ".MuiDataGrid-columnHeader",
        '[role="columnheader"]',
    ]:
        locator = page.locator(selector)

        for i in range(await locator.count()):
            try:
                item = locator.nth(i)
                if not await item.is_visible():
                    continue

                text = clean_text(await item.inner_text())

                if text and text not in seen:
                    seen.add(text)
                    headers.append(text)
            except Exception:
                pass

    return headers


async def extract_structured_page(page):
    html_rows = await extract_html_table(page)
    grid_rows = await extract_datagrid(page)
    headers = await extract_headers(page)

    return {
        "url": page.url,
        "headers": headers,
        "html_rows": html_rows,
        "grid_rows": grid_rows,
        "fullText": await page.locator("body").inner_text(),
    }


async def click_visible_exact_text(page, text):
    matches = page.get_by_text(text, exact=True)

    for i in range(await matches.count()):
        try:
            item = matches.nth(i)
            if await item.is_visible():
                await item.click()
                return True
        except Exception:
            continue

    return False


async def dismiss_blocking_dialogs(page):
    """Close PropFinder install/help dialogs that cover table controls."""
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass

    for selector in [
        '[aria-label="Close"]',
        'button:has-text("Close")',
        'button:has-text("×")',
    ]:
        locator = page.locator(selector)
        for i in range(await locator.count()):
            try:
                item = locator.nth(i)
                if await item.is_visible():
                    await item.click(timeout=1500)
                    await page.wait_for_timeout(300)
                    return
            except Exception:
                continue


async def collect_lazy_rows(page, max_scrolls=160):
    """Collect semantic, MUI, or native table rows from a lazy-loaded view."""
    rows_seen = {}
    selectors = [
        "tbody tr",
        ".MuiDataGrid-row",
        '[role="rowgroup"] [role="row"]',
    ]

    async def collect_visible():
        for selector in selectors:
            rows = page.locator(selector)
            for i in range(await rows.count()):
                row = rows.nth(i)
                try:
                    if not await row.is_visible():
                        continue
                    cells = row.locator(
                        'th, td, [role="gridcell"], .MuiDataGrid-cell'
                    )
                    values = []
                    for j in range(await cells.count()):
                        value = clean_text(await cells.nth(j).inner_text())
                        if value:
                            values.append(value)
                    if not values:
                        text = clean_text(await row.inner_text())
                        values = [
                            clean_text(value)
                            for value in text.split("\n")
                            if clean_text(value)
                        ]
                    if values:
                        rows_seen["|".join(values)] = values
                except Exception:
                    continue

    await collect_visible()
    unchanged = 0

    for _ in range(max_scrolls):
        before = len(rows_seen)
        state = await page.evaluate(
            """() => {
                const containers = Array.from(document.querySelectorAll('*'))
                    .filter(el => {
                        const css = getComputedStyle(el);
                        return /(auto|scroll)/.test(css.overflowY) &&
                            el.scrollHeight > el.clientHeight + 20 &&
                            !!el.querySelector(
                                'tbody tr, .MuiDataGrid-row, [role="row"]'
                            );
                    })
                    .sort((a, b) => b.clientHeight - a.clientHeight);
                const el = containers[0];
                if (!el) {
                    window.scrollBy(0, Math.max(600, innerHeight * .8));
                    return { internal: false, bottom: false };
                }
                // PropFinder appends the next batch when the table reaches
                // its bottom. Jump there directly instead of walking every
                // visible row, which is much faster for 1,000+ CFB props.
                el.scrollTop = el.scrollHeight;
                el.dispatchEvent(new Event('scroll', { bubbles: true }));
                return {
                    internal: true,
                    bottom: el.scrollTop + el.clientHeight >= el.scrollHeight - 8
                };
            }"""
        )
        await page.wait_for_timeout(900)
        await collect_visible()
        unchanged = unchanged + 1 if len(rows_seen) == before else 0

        if state.get("bottom") and unchanged >= 2:
            break
        if unchanged >= 5:
            break

    return list(rows_seen.values())


async def propfinder_loaded_count(page):
    text = clean_text(await page.locator("body").inner_text())
    match = re.search(
        r"(\d[\d,]*)\s+of\s+(\d[\d,]*)\s+loaded",
        text,
        re.IGNORECASE,
    )
    if not match:
        return {"site_loaded": None, "site_total": None}
    return {
        "site_loaded": int(match.group(1).replace(",", "")),
        "site_total": int(match.group(2).replace(",", "")),
    }


async def select_prop_direction(page, direction):
    """Select the actual OVER/UNDER control and verify its active state."""
    clicked = await page.evaluate(
        """direction => {
            const exact = value =>
                (value || '').trim().toUpperCase() === direction;
            const buttons = Array.from(document.querySelectorAll('button'));
            let target = buttons.find(el => exact(el.innerText));
            if (!target) {
                const label = Array.from(document.querySelectorAll('*'))
                    .find(el => exact(el.innerText) && el.children.length === 0);
                target = label && label.closest('button');
            }
            if (!target) return false;
            target.click();
            return true;
        }""",
        direction,
    )
    await page.wait_for_timeout(2500)
    return clicked


def read_export_csv(filepath):
    """Read a PropFinder CSV export with delimiter/encoding tolerance."""
    raw = None
    for encoding in ["utf-8-sig", "utf-8", "cp1252"]:
        try:
            with open(filepath, "r", encoding=encoding, newline="") as handle:
                raw = handle.read()
            break
        except UnicodeDecodeError:
            continue

    if raw is None:
        raise RuntimeError(f"Could not decode PropFinder export: {filepath}")

    try:
        dialect = csv.Sniffer().sniff(raw[:8192], delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(raw.splitlines(), dialect=dialect)
    rows = [
        {
            clean_text(key): clean_text(value)
            for key, value in row.items()
            if key is not None
        }
        for row in reader
    ]
    return list(reader.fieldnames or []), rows


async def export_prop_view(page, scrape_date, direction):
    """Download the complete filtered prop table instead of its virtual DOM."""
    export_control = page.get_by_text("Export", exact=True)
    visible_export = None
    for i in range(await export_control.count()):
        candidate = export_control.nth(i)
        if await candidate.is_visible():
            visible_export = candidate
            break

    if visible_export is None:
        raise RuntimeError("Visible CFB Export control not found")

    async with page.expect_download(timeout=30_000) as download_info:
        await visible_export.click()

    download = await download_info.value
    filepath = f"logs/{scrape_date}_cfb_props_{direction.lower()}.csv"
    await download.save_as(filepath)
    headers, rows = read_export_csv(filepath)
    return filepath, headers, rows


async def collect_power_rating_rows(page, max_scrolls=80):
    """Collect the CSS-grid power-rating rows (they are not table elements)."""
    rows_seen = {}

    async def collect():
        rows = await page.evaluate(
            r"""() => {
                const normalize = text => (text || '').trim()
                    .split('\n').map(v => v.trim()).filter(Boolean);
                const isRow = el => {
                    const lines = normalize(el.innerText);
                    return lines.length >= 9 && lines.length <= 24 &&
                        /^\d{1,3}$/.test(lines[0]) &&
                        lines[1] && !/^\d/.test(lines[1]);
                };
                return Array.from(document.querySelectorAll('div'))
                    .filter(isRow)
                    .filter(el => !Array.from(el.children).some(isRow))
                    .map(el => normalize(el.innerText));
            }"""
        )
        for row in rows:
            rows_seen["|".join(row)] = row

    for _ in range(max_scrolls):
        await collect()
        state = await page.evaluate(
            r"""() => {
                const containers = Array.from(document.querySelectorAll('*'))
                    .filter(el => {
                        const css = getComputedStyle(el);
                        return /(auto|scroll)/.test(css.overflowY) &&
                            el.scrollHeight > el.clientHeight + 20 &&
                            /teams\s*·\s*sorted by rating/i.test(
                                el.parentElement?.innerText || ''
                            );
                    })
                    .sort((a, b) => b.clientHeight - a.clientHeight);
                const el = containers[0];
                if (!el) return { found: false, bottom: true };
                el.scrollTop = Math.min(
                    el.scrollTop + Math.max(500, el.clientHeight * .8),
                    el.scrollHeight
                );
                el.dispatchEvent(new Event('scroll', { bubbles: true }));
                return {
                    found: true,
                    bottom: el.scrollTop + el.clientHeight >= el.scrollHeight - 8
                };
            }"""
        )
        await page.wait_for_timeout(350)
        if state.get("bottom"):
            await collect()
            break

    return list(rows_seen.values())


async def discover_cfb_pages(page):
    """Resolve the current CFB submenu hrefs instead of assuming URL slugs."""
    await navigate(page, CFB_URLS["cfb_props"], 6000)
    await dismiss_blocking_dialogs(page)

    # These routes are verified. Menu discovery below remains in place so a
    # future PropFinder route change can replace them automatically.
    discovered = dict(CFB_URLS)

    # Opening the CFB menu makes submenu links available on builds that do not
    # render them until interaction.
    await click_visible_exact_text(page, "CFB")
    await page.wait_for_timeout(700)

    links = page.locator("a[href]")
    for i in range(await links.count()):
        link = links.nth(i)
        try:
            label = clean_text(await link.inner_text())
            href = await link.get_attribute("href")
            if not href:
                continue
            for name, labels in CFB_PAGE_LABELS.items():
                if any(candidate.lower() in label.lower() for candidate in labels):
                    discovered[name] = (
                        href if href.startswith("http") else f"{BASE_URL}{href}"
                    )
        except Exception:
            continue

    return discovered


async def scrape_cfb_props(page, scrape_date, url):
    print("\n🏈 Scraping CFB player props...", flush=True)
    await navigate(page, url, 7000)
    await dismiss_blocking_dialogs(page)

    result = {
        "date": scrape_date,
        "league": "CFB",
        "url": page.url,
        "alternate_lines": False,
        "views": {},
    }

    for direction in ["OVER", "UNDER"]:
        # Reload between views so the virtual table starts at the top and the
        # second direction cannot inherit the first direction's scroll state.
        await navigate(page, url, 4000)
        await dismiss_blocking_dialogs(page)
        selected = await select_prop_direction(page, direction)
        count = await propfinder_loaded_count(page)

        export_error = None
        export_path = None
        headers = []
        rows = []
        try:
            export_path, headers, rows = await export_prop_view(
                page, scrape_date, direction
            )
        except Exception as error:
            export_error = f"{type(error).__name__}: {error!r}"
            print(
                f"   ⚠️ {direction} export failed; using DOM fallback: "
                f"{export_error}",
                flush=True,
            )
            rows = await collect_lazy_rows(page)
            headers = await extract_headers(page)

        result["views"][direction.lower()] = {
            "selected": selected,
            "source": "csv_export" if export_path else "dom_fallback",
            "export_path": export_path,
            "export_error": export_error,
            "headers": headers,
            "rows": rows,
            "scraped_rows": len(rows),
            **count,
            "complete": len(rows) > 0 and (
                count["site_total"] is None or len(rows) >= count["site_total"]
            ),
        }

        await page.screenshot(
            path=f"logs/cfb_props_{direction.lower()}.png",
            full_page=True,
        )
        print(
            f"   ✅ {direction}: {len(rows)} unique rows "
            f"({count['site_loaded']} of {count['site_total']} site-loaded)",
            flush=True,
        )

    save_json(scrape_date, "cfb_props", result)
    return result


async def scrape_cfb_games(page, scrape_date, url):
    print("\n🏟️ Scraping CFB games & projections...", flush=True)
    await navigate(page, url, 7000)

    # Load every game card on pages that append content while scrolling.
    previous_height = 0
    for _ in range(80):
        height = await page.evaluate("document.body.scrollHeight")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(500)
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == previous_height == height:
            break
        previous_height = new_height

    cards = await page.evaluate(
        r"""() => {
            const markers = Array.from(document.querySelectorAll('*'))
                .filter(el => /MODEL PICKS\s*[•·-]\s*BEST PRICE/i.test(
                    el.textContent || ''
                ));
            const output = [];
            const seen = new Set();
            for (const marker of markers) {
                let el = marker;
                while (el.parentElement &&
                       (el.innerText || '').length < 180 &&
                       el.parentElement.innerText.length < 1800) {
                    el = el.parentElement;
                }
                const text = (el.innerText || '').trim();
                if (text && text.length < 2500 && !seen.has(text)) {
                    seen.add(text);
                    output.push(text.split('\n').map(v => v.trim()).filter(Boolean));
                }
            }
            return output;
        }"""
    )

    # The DOM search returns each full game card and its nested model-picks
    # block. Only full cards begin with PROJECTED or FINAL.
    cards = [
        card for card in cards
        if card and card[0].upper() in {"PROJECTED", "FINAL"}
    ]

    data = {
        "date": scrape_date,
        "league": "CFB",
        "url": page.url,
        "cards": cards,
        "card_count": len(cards),
        "fullText": await page.locator("body").inner_text(),
    }
    await page.screenshot(path="logs/cfb_games.png", full_page=True)
    save_json(scrape_date, "cfb_games", data)
    print(f"   ✅ CFB games: {len(cards)} cards", flush=True)
    return data


async def scrape_cfb_power_ratings(page, scrape_date, url):
    print("\n📊 Scraping CFB power ratings...", flush=True)
    await navigate(page, url, 6000)
    rows = await collect_power_rating_rows(page, max_scrolls=80)
    data = {
        "date": scrape_date,
        "league": "CFB",
        "url": page.url,
        "headers": [
            "RANK", "TEAM", "CONF", "REC", "RATING", "SPR",
            "WOW", "YTD", "TREND", "OFF", "OFF_RANK", "DEF",
            "DEF_RANK",
        ],
        "rows": rows,
        "team_count": len(rows),
    }
    await page.screenshot(path="logs/cfb_power_ratings.png", full_page=True)
    save_json(scrape_date, "cfb_power_ratings", data)
    print(f"   ✅ CFB power ratings: {len(rows)} teams", flush=True)
    return data


async def run_cfb_scraper():
    scrape_date = scrape_date_string()
    results = {}
    print(f"\n{'=' * 50}", flush=True)
    print(f"🏈 CFB Picks Bot — Scraping {scrape_date}", flush=True)
    print(f"{'=' * 50}\n", flush=True)
    os.makedirs("logs", exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=os.getenv("HEADLESS", "false").lower() == "true"
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        page.set_default_timeout(30_000)
        page.set_default_navigation_timeout(45_000)

        try:
            await asyncio.wait_for(login(page), timeout=60)
            urls = await discover_cfb_pages(page)
            print(f"🔗 CFB pages discovered: {urls}", flush=True)

            jobs = [
                ("cfb_props", scrape_cfb_props, 240),
                ("cfb_games", scrape_cfb_games, 120),
                ("cfb_power_ratings", scrape_cfb_power_ratings, 90),
            ]

            for name, scraper_fn, timeout_seconds in jobs:
                if name not in urls:
                    print(f"⚠️ CFB submenu URL not found for {name}", flush=True)
                    results[name] = {}
                    continue
                try:
                    results[name] = await asyncio.wait_for(
                        scraper_fn(page, scrape_date, urls[name]),
                        timeout=timeout_seconds,
                    )
                except Exception as error:
                    print(
                        f"❌ {name} failed: {type(error).__name__}: "
                        f"{error!r}",
                        flush=True,
                    )
                    results[name] = {}

            summary = {
                "date": scrape_date,
                "league": "CFB",
                "sources": {
                    "cfb_props": bool(results.get("cfb_props")),
                    "cfb_games": bool(results.get("cfb_games")),
                    "cfb_power_ratings": bool(results.get("cfb_power_ratings")),
                },
            }
            save_json(scrape_date, "cfb_summary", summary)
        finally:
            await browser.close()

    return results


# ─────────────────────────────────────────────
# NFL SCRAPERS
# ─────────────────────────────────────────────

async def export_nfl_prop_view(page, scrape_date, direction):
    export_control = page.get_by_text("Export", exact=True)
    visible_export = None
    for i in range(await export_control.count()):
        candidate = export_control.nth(i)
        if await candidate.is_visible():
            visible_export = candidate
            break

    if visible_export is None:
        raise RuntimeError("Visible NFL Export control not found")

    async with page.expect_download(timeout=30_000) as download_info:
        await visible_export.click()

    download = await download_info.value
    filepath = f"logs/{scrape_date}_nfl_props_{direction.lower()}.csv"
    await download.save_as(filepath)
    headers, rows = read_export_csv(filepath)
    return filepath, headers, rows


async def scrape_nfl_props(page, scrape_date, url):
    print("\n🏈 Scraping NFL player props...", flush=True)
    result = {
        "date": scrape_date,
        "league": "NFL",
        "url": url,
        "alternate_lines": False,
        "early_season_note": (
            "Prior-season hit rates require reduced weight until Week 5."
        ),
        "views": {},
    }

    for direction in ["OVER", "UNDER"]:
        await navigate(page, url, 4500)
        await dismiss_blocking_dialogs(page)
        selected = await select_prop_direction(page, direction)
        count = await propfinder_loaded_count(page)

        export_error = None
        export_path = None
        headers = []
        rows = []
        try:
            export_path, headers, rows = await export_nfl_prop_view(
                page, scrape_date, direction
            )
        except Exception as error:
            export_error = f"{type(error).__name__}: {error!r}"
            print(
                f"   ⚠️ {direction} export failed; using DOM fallback: "
                f"{export_error}",
                flush=True,
            )
            rows = await collect_lazy_rows(page)
            headers = await extract_headers(page)

        result["views"][direction.lower()] = {
            "selected": selected,
            "source": "csv_export" if export_path else "dom_fallback",
            "export_path": export_path,
            "export_error": export_error,
            "headers": headers,
            "rows": rows,
            "scraped_rows": len(rows),
            **count,
            "complete": len(rows) > 0 and (
                count["site_total"] is None or len(rows) >= count["site_total"]
            ),
        }

        await page.screenshot(
            path=f"logs/nfl_props_{direction.lower()}.png",
            full_page=True,
        )
        print(
            f"   ✅ {direction}: {len(rows)} exported rows "
            f"({count['site_loaded']} of {count['site_total']} visible state)",
            flush=True,
        )

    save_json(scrape_date, "nfl_props", result)
    return result


async def scrape_nfl_games(page, scrape_date, url):
    print("\n🏟️ Scraping NFL games & projections...", flush=True)
    await navigate(page, url, 6500)

    cards = await page.evaluate(
        r"""() => {
            const normalize = text => (text || '').trim()
                .split('\n').map(v => v.trim()).filter(Boolean);
            const candidates = Array.from(document.querySelectorAll('div'))
                .filter(el => {
                    const lines = normalize(el.innerText);
                    return lines[0] === 'PROJECTED' &&
                        lines.some(v => /MODEL PICKS\s*[•·-]\s*BEST PRICE/i.test(v)) &&
                        lines.length >= 15 && lines.length <= 45;
                });
            return candidates
                .filter(el => !Array.from(el.children).some(child => {
                    const lines = normalize(child.innerText);
                    return lines[0] === 'PROJECTED' &&
                        lines.some(v => /MODEL PICKS\s*[•·-]\s*BEST PRICE/i.test(v));
                }))
                .map(el => normalize(el.innerText));
        }"""
    )

    deduped = []
    seen = set()
    for card in cards:
        key = "|".join(card)
        if key not in seen:
            seen.add(key)
            deduped.append(card)

    data = {
        "date": scrape_date,
        "league": "NFL",
        "url": page.url,
        "early_season_weight": {
            "weeks_1_2_prior_season": 0.70,
            "weeks_3_4_prior_season": 0.40,
            "week_5_plus_prior_season": 0.15,
        },
        "cards": deduped,
        "card_count": len(deduped),
        "fullText": await page.locator("body").inner_text(),
    }
    await page.screenshot(path="logs/nfl_games.png", full_page=True)
    save_json(scrape_date, "nfl_games", data)
    print(f"   ✅ NFL games: {len(deduped)} cards", flush=True)
    return data


async def extract_repeated_content_blocks(page, min_lines=5, max_lines=30):
    """Capture smallest repeated card/row divs for non-table NFL pages."""
    return await page.evaluate(
        r"""([minLines, maxLines]) => {
            const normalize = text => (text || '').trim()
                .split('\n').map(v => v.trim()).filter(Boolean);
            const valid = el => {
                const n = normalize(el.innerText).length;
                return n >= minLines && n <= maxLines;
            };
            const rows = Array.from(document.querySelectorAll('div'))
                .filter(valid)
                .filter(el => !Array.from(el.children).some(valid))
                .map(el => normalize(el.innerText));
            const seen = new Set();
            return rows.filter(row => {
                const key = row.join('|');
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
        }""",
        [min_lines, max_lines],
    )


async def scrape_nfl_context_page(page, scrape_date, name, url):
    print(f"\n📄 Scraping {name}...", flush=True)
    await navigate(page, url, 6000)
    await dismiss_blocking_dialogs(page)

    # Traverse the page once so lazy content has a chance to render.
    previous_height = 0
    for _ in range(30):
        height = await page.evaluate("document.body.scrollHeight")
        await page.evaluate("window.scrollBy(0, Math.max(600, innerHeight * .8))")
        await page.wait_for_timeout(250)
        if height == previous_height:
            break
        previous_height = height

    structured = await extract_structured_page(page)
    blocks = await extract_repeated_content_blocks(page)
    images = await page.locator("img").evaluate_all(
        "els => els.map(el => ({alt: el.alt || '', title: el.title || ''}))"
    )

    data = {
        "date": scrape_date,
        "league": "NFL",
        "url": page.url,
        "headers": structured.get("headers", []),
        "html_rows": structured.get("html_rows", []),
        "grid_rows": structured.get("grid_rows", []),
        "blocks": blocks,
        "images": images,
        "fullText": structured.get("fullText", ""),
    }
    await page.screenshot(path=f"logs/{name}.png", full_page=True)
    save_json(scrape_date, name, data)
    print(
        f"   ✅ {name}: {len(data['html_rows'])} HTML rows, "
        f"{len(data['grid_rows'])} grid rows, {len(blocks)} blocks",
        flush=True,
    )
    return data


async def run_nfl_scraper():
    scrape_date = scrape_date_string()
    results = {}
    print(f"\n{'=' * 50}", flush=True)
    print(f"🏈 NFL Picks Bot — Scraping {scrape_date}", flush=True)
    print(f"{'=' * 50}\n", flush=True)
    os.makedirs("logs", exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=os.getenv("HEADLESS", "false").lower() == "true"
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        page.set_default_timeout(30_000)
        page.set_default_navigation_timeout(45_000)

        try:
            await asyncio.wait_for(login(page), timeout=60)
            jobs = [
                ("nfl_props", scrape_nfl_props, 240),
                ("nfl_games", scrape_nfl_games, 90),
            ]
            for name, fn, timeout_seconds in jobs:
                try:
                    results[name] = await asyncio.wait_for(
                        fn(page, scrape_date, NFL_URLS[name]),
                        timeout=timeout_seconds,
                    )
                except Exception as error:
                    print(
                        f"❌ {name} failed: {type(error).__name__}: {error!r}",
                        flush=True,
                    )
                    results[name] = {}

            for name in [
                "nfl_weather",
                "nfl_home_field_advantage",
                "nfl_odds_discrepancies",
            ]:
                try:
                    results[name] = await asyncio.wait_for(
                        scrape_nfl_context_page(
                            page, scrape_date, name, NFL_URLS[name]
                        ),
                        timeout=90,
                    )
                except Exception as error:
                    print(
                        f"❌ {name} failed: {type(error).__name__}: {error!r}",
                        flush=True,
                    )
                    results[name] = {}

            summary = {
                "date": scrape_date,
                "league": "NFL",
                "early_season_policy": (
                    "Weeks 1-2: 70% prior/30% current; Weeks 3-4: "
                    "40% prior/60% current; Week 5+: 15% prior/85% current."
                ),
                "sources": {
                    name: bool(data) for name, data in results.items()
                },
            }
            save_json(scrape_date, "nfl_summary", summary)
        finally:
            await browser.close()

    return results


async def select_compare_window(page, window_name):
    """
    Find the Volume Trends compare dropdown and select L3/L5/L10/L15.
    """
    comboboxes = page.locator('[role="combobox"]')
    target_combo = None

    for i in range(await comboboxes.count()):
        combo = comboboxes.nth(i)

        try:
            text = clean_text(await combo.inner_text()).upper()

            if any(value in text for value in ["L3", "L5", "L10", "L15"]):
                target_combo = combo
                break
        except Exception:
            continue

    if target_combo is not None:
        try:
            await target_combo.click()
            await page.wait_for_timeout(800)

            if await click_visible_exact_text(page, window_name):
                await page.wait_for_timeout(3500)
                return True
        except Exception:
            pass

    if await click_visible_exact_text(page, window_name):
        await page.wait_for_timeout(3500)
        return True

    print(f"   ⚠️ Could not automatically select Volume Trends {window_name}")
    return False


# ─────────────────────────────────────────────
# MLB SCRAPERS
# ─────────────────────────────────────────────

async def scrape_page(page, name, url):
    print(f"\n📄 Scraping {name}...")
    await navigate(page, url, 3000)
    await page.screenshot(path=f"logs/{name}.png")

    content = await page.evaluate(
        """() => {
            const rows = Array.from(document.querySelectorAll("tr"))
                .map(r => r.innerText.trim())
                .filter(Boolean);

            const cells = Array.from(document.querySelectorAll("td, th"))
                .map(c => c.innerText.trim())
                .filter(Boolean);

            const fullText = document.body.innerText;

            return { rows, cells, fullText };
        }"""
    )

    print(
        f"   ✅ {name}: {len(content['rows'])} rows, "
        f"{len(content['cells'])} cells found"
    )
    return content


async def scrape_exit_velo(page, url):
    print("\n📄 Scraping exit_velo...")
    await navigate(page, url, 2000)

    try:
        await page.get_by_role("button", name="SEARCH").click()
        await page.wait_for_timeout(3000)
        print("   ✅ Search clicked")
    except Exception as e:
        print(f"   ⚠️ Could not click search: {e}")

    await page.screenshot(path="logs/exit_velo.png")

    content = await page.evaluate(
        """() => {
            const rows = Array.from(document.querySelectorAll("tr"))
                .map(r => r.innerText.trim())
                .filter(Boolean);

            const cells = Array.from(document.querySelectorAll("td, th"))
                .map(c => c.innerText.trim())
                .filter(Boolean);

            const fullText = document.body.innerText;

            return { rows, cells, fullText };
        }"""
    )

    print(
        f"   ✅ exit_velo: {len(content['rows'])} rows, "
        f"{len(content['cells'])} cells found"
    )

    return content


async def scrape_projections(page, url):
    print("\n📄 Scraping projections...")
    await navigate(page, url, 3000)

    try:
        await page.get_by_text("CONSENSUS").click()
        await page.wait_for_timeout(2000)
        print("   ✅ Switched to CONSENSUS tab")
    except Exception as e:
        print(f"   ⚠️ Could not click CONSENSUS: {e}")

    await page.screenshot(path="logs/projections.png")

    content = await page.evaluate(
        """() => ({
            rows: [],
            cells: [],
            fullText: document.body.innerText
        })"""
    )

    game_count = content["fullText"].count("Proj Runs") // 2
    print(f"   ✅ projections: {game_count} games found")

    return content


# ─────────────────────────────────────────────
# NRFI SCRAPER
# ─────────────────────────────────────────────

async def scrape_nrfi(page, scrape_date):
    """Scrape NRFI/YRFI Research page."""
    import re

    print("\n📄 Scraping nrfi...")

    await navigate(page, NRFI_URL, 4000)

    body_text = await page.locator("body").inner_text()

    if len(body_text.strip()) < 200:
        print("   ❌ Page body too short — likely not logged in")
        await page.screenshot(path="logs/nrfi_empty.png")
        return {}

    result = {
        "team_records": [],
        "batting_records": [],
        "pitcher_records": [],
        "matchups": [],
        "nrfi_scores": [],
        "date": scrape_date,
    }

    def get_tab_selector(name):
        safe_name = json.dumps(name)

        return f"""
            Array.from(document.querySelectorAll(
                'button, [role="tab"], li, div'
            ))
            .find(el => el.innerText.trim() === {safe_name})
            ?.click();
        """

    async def grab_rows():
        await page.wait_for_timeout(2000)

        return await page.evaluate(
            """() => {
                return Array.from(document.querySelectorAll("tr"))
                    .map(r => r.innerText.trim())
                    .filter(Boolean);
            }"""
        )

    try:
        rows = await grab_rows()
        result["team_records"] = rows
        print(f"   ✅ Team Records: {len(rows)} rows")
    except Exception as e:
        print(f"   ⚠️ Team Records error: {e}")

    try:
        await page.evaluate(get_tab_selector("Batting Records"))
        rows = await grab_rows()
        result["batting_records"] = rows
        print(f"   ✅ Batting Records: {len(rows)} rows")
    except Exception as e:
        print(f"   ⚠️ Batting Records error: {e}")

    try:
        await page.evaluate(get_tab_selector("Pitcher Records"))
        rows = await grab_rows()
        result["pitcher_records"] = rows
        print(f"   ✅ Pitcher Records: {len(rows)} rows")
    except Exception as e:
        print(f"   ⚠️ Pitcher Records error: {e}")

    try:
        await page.evaluate(get_tab_selector("Today's Matchups"))
        await page.wait_for_timeout(3000)

        matchups_raw = await page.evaluate(
            """() => {
                const cards = Array.from(
                    document.querySelectorAll("table")
                )
                .map(table => {
                    return Array.from(table.querySelectorAll("tr"))
                        .map(r => r.innerText.trim())
                        .filter(Boolean);
                })
                .filter(rows => rows.length >= 2);

                return {
                    cards,
                    fullText: document.body.innerText
                };
            }"""
        )

        if matchups_raw["cards"]:
            result["matchups"] = matchups_raw["cards"]
        else:
            result["matchups"] = [
                {"raw_text": matchups_raw["fullText"][:8000]}
            ]

        score_matches = re.findall(
            r"NRFI Score\s*[\n\r]*\s*([\d.]+)",
            matchups_raw["fullText"],
        )

        result["nrfi_scores"] = score_matches

        print(
            f"   ✅ Today's Matchups: "
            f"{len(result['matchups'])} cards, "
            f"{len(result['nrfi_scores'])} NRFI scores"
        )

    except Exception as e:
        print(f"   ⚠️ Today's Matchups error: {e}")

        try:
            full_text = await page.locator("body").inner_text()
            result["matchups"] = [{"raw_text": full_text[:8000]}]
        except Exception:
            pass

    await page.screenshot(path="logs/nrfi.png")

    filepath = f"logs/{scrape_date}_nrfi.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"   💾 NRFI data saved to {filepath}")

    return result


async def run_nrfi_scraper(scrape_date):
    headless_mode = os.getenv("HEADLESS", "false").lower() == "true"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless_mode)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900}
        )
        page = await context.new_page()

        try:
            await login(page)
            return await scrape_nrfi(page, scrape_date)

        except Exception as e:
            print(f"   ❌ NRFI scraper error: {e}")
            return {}

        finally:
            await browser.close()


# ─────────────────────────────────────────────
# NBA SCRAPERS
# ─────────────────────────────────────────────

async def scrape_nba_team_stats(page, url):
    print("\n📄 Scraping nba_team_stats...")
    await navigate(page, url, 5000)
    await page.evaluate("window.scrollTo(0, 300)")
    await page.wait_for_timeout(2000)
    await page.screenshot(path="logs/nba_team_stats.png")

    content = await page.evaluate(
        """() => {
            const rows = Array.from(document.querySelectorAll("tr"))
                .map(r => r.innerText.trim())
                .filter(Boolean);

            return {
                rows,
                fullText: document.body.innerText
            };
        }"""
    )

    print(f"   ✅ nba_team_stats: {len(content['rows'])} rows")
    return content


async def scrape_nba_player_stats(page, url):
    print("\n📄 Scraping nba_player_stats...")
    await navigate(page, url, 5000)
    await page.evaluate("window.scrollTo(0, 500)")
    await page.wait_for_timeout(3000)
    await page.screenshot(path="logs/nba_player_stats.png")

    content = await page.evaluate(
        """() => {
            const rows = Array.from(document.querySelectorAll("tr"))
                .map(r => r.innerText.trim())
                .filter(Boolean);

            return {
                rows,
                fullText: document.body.innerText
            };
        }"""
    )

    print(f"   ✅ nba_player_stats: {len(content['rows'])} rows")
    return content


async def scrape_basketball_research(page, league, scrape_date):
    name = f"{league}_research"
    url = f"{BASE_URL}/{league}"

    print(f"\n📄 Scraping {name}...")

    try:
        await navigate(page, url, 8000)

        rows = await extract_datagrid(
            page,
            max_scrolls=60,
            step=400,
        )

        print(f"   ✅ {name}: {len(rows)} rows")

        data = {
            "league": league,
            "date": scrape_date,
            "url": page.url,
            "headers": await extract_headers(page),
            "rows": rows,
            "total": len(rows),
        }

        await page.screenshot(
            path=f"logs/{name}.png",
            full_page=True,
        )

        save_json(scrape_date, name, data)

        return data

    except Exception as e:
        print(f"   ❌ {name} scrape failed: {e}")

        return {
            "league": league,
            "date": scrape_date,
            "rows": [],
            "total": 0,
        }


async def scrape_nba_def_matchups(page, url):
    print("\n📄 Scraping nba_def_matchups...")
    await navigate(page, url, 5000)

    try:
        await page.wait_for_selector("tr", timeout=50000)
    except Exception:
        print("   ⚠️ Table timeout")

    await page.evaluate("window.scrollTo(0, 300)")
    await page.wait_for_timeout(10000)

    try:
        await (
            page.locator(".MuiChip-label")
            .get_by_text("PG", exact=True)
            .first
            .click()
        )

        await page.wait_for_timeout(1500)

        for pos in ["SG", "PF", "SF", "C"]:
            try:
                await page.get_by_role(
                    "option",
                    name=pos,
                    exact=True,
                ).click()

                await page.wait_for_timeout(400)
            except Exception:
                pass

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(3000)

    except Exception as e:
        print(f"   ⚠️ Position dropdown error: {e}")

    await page.screenshot(path="logs/nba_def_matchups.png")

    content = await page.evaluate(
        """() => {
            const rows = Array.from(document.querySelectorAll("tr"))
                .map(r => r.innerText.trim())
                .filter(Boolean);

            return {
                rows,
                fullText: document.body.innerText
            };
        }"""
    )

    print(f"   ✅ nba_def_matchups: {len(content['rows'])} rows")

    return content


async def scrape_nba_hit_rate(page, url):
    print("\n📄 Scraping nba_hit_rate...")
    await navigate(page, url, 5000)
    await page.evaluate("window.scrollTo(0, 300)")
    await page.wait_for_timeout(2000)

    try:
        await page.get_by_text(
            "Last 5 Games",
            exact=True,
        ).first.click()

        await page.wait_for_timeout(1000)

        await page.get_by_role(
            "option",
            name="2025-26 Season",
        ).click()

        await page.wait_for_timeout(2000)

    except Exception as e:
        print(f"   ⚠️ Game Count error: {e}")

    categories = [
        "Points",
        "Rebounds",
        "Assists",
        "Three Pointers",
        "Points + Rebounds",
        "Points + Assists",
        "Rebounds + Assists",
        "Pts + Reb + Ast",
    ]

    all_data = {}
    current_cat = "Points"

    for cat in categories:
        try:
            await page.get_by_text(
                current_cat,
                exact=True,
            ).first.click()

            await page.wait_for_timeout(1500)

            await page.get_by_role(
                "option",
                name=cat,
                exact=True,
            ).click()

            await page.wait_for_timeout(2500)

            current_cat = cat

            all_data[cat] = await page.locator("body").inner_text()

        except Exception as e:
            print(f"   ⚠️ {cat} error: {e}")
            all_data[cat] = ""
            current_cat = "Points"

    await page.screenshot(path="logs/nba_hit_rate.png")

    print(f"   ✅ nba_hit_rate: {len(all_data)} categories")

    return all_data


async def scrape_nba_injury_reports(page, url):
    print("\n📄 Scraping nba_injury_reports...")
    await navigate(page, url, 5000)
    await page.evaluate("window.scrollTo(0, 300)")
    await page.wait_for_timeout(2000)
    await page.screenshot(path="logs/nba_injury_reports.png")

    content = await page.evaluate(
        """() => {
            const rows = Array.from(document.querySelectorAll("tr"))
                .map(r => r.innerText.trim())
                .filter(Boolean);

            return {
                rows,
                fullText: document.body.innerText
            };
        }"""
    )

    print(f"   ✅ nba_injury_reports: {len(content['rows'])} rows")

    return content


async def scrape_nba_lineups(page, url):
    print("\n📄 Scraping nba_lineups...")
    await navigate(page, url, 5000)

    try:
        await page.get_by_text("ALL TEAMS").click()
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"   ⚠️ ALL TEAMS click error: {e}")

    for scroll_pos in [500, 1000, 1500, 2000, 2500]:
        await page.evaluate(f"window.scrollTo(0, {scroll_pos})")
        await page.wait_for_timeout(800)

    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(1000)
    await page.screenshot(path="logs/nba_lineups.png")

    content = {
        "fullText": await page.locator("body").inner_text()
    }

    print(f"   ✅ nba_lineups: {len(content['fullText'])} chars")

    return content


# ─────────────────────────────────────────────
# WNBA SCRAPERS
# ─────────────────────────────────────────────

async def scrape_wnba_simple_page(page, name, url):
    print(f"\n📄 Scraping {name}...")
    await navigate(page, url, 7000)

    await page.evaluate("window.scrollTo(0, 500)")
    await page.wait_for_timeout(1500)

    data = await extract_structured_page(page)

    await page.screenshot(
        path=f"logs/{name}.png",
        full_page=True,
    )

    row_count = max(
        len(data["html_rows"]),
        len(data["grid_rows"]),
    )

    print(
        f"   ✅ {name}: "
        f"{len(data['html_rows'])} HTML rows, "
        f"{len(data['grid_rows'])} DataGrid rows"
    )

    if row_count == 0:
        print("   ⚠️ No structured rows detected")

    return data


async def scrape_wnba_research(page, scrape_date):
    return await scrape_basketball_research(
        page,
        "wnba",
        scrape_date,
    )


async def scrape_wnba_player_stats(page, url):
    return await scrape_wnba_simple_page(
        page,
        "wnba_player_stats",
        url,
    )


async def scrape_wnba_team_stats(page, url):
    return await scrape_wnba_simple_page(
        page,
        "wnba_team_stats",
        url,
    )


async def scrape_wnba_hit_rate(page, url):
    return await scrape_wnba_simple_page(
        page,
        "wnba_hit_rate",
        url,
    )


async def scrape_wnba_injury_reports(page, url):
    return await scrape_wnba_simple_page(
        page,
        "wnba_injury_reports",
        url,
    )


async def scrape_wnba_volume_trends(page, url):
    print("\n📄 Scraping wnba_volume_trends...")
    await navigate(page, url, 9000)

    result = {
        "url": page.url,
        "headers": await extract_headers(page),
        "default": await extract_structured_page(page),
        "windows": {},
    }

    await page.screenshot(
        path="logs/wnba_volume_trends_default.png",
        full_page=True,
    )

    for window in ["L3", "L5", "L10", "L15"]:
        print(f"   🔎 Volume Trends {window}...")

        selected = await select_compare_window(
            page,
            window,
        )

        if not selected:
            result["windows"][window] = {
                "selected": False,
                "headers": [],
                "html_rows": [],
                "grid_rows": [],
            }
            continue

        window_data = await extract_structured_page(page)
        window_data["selected"] = True
        result["windows"][window] = window_data

        await page.screenshot(
            path=f"logs/wnba_volume_trends_{window.lower()}.png",
            full_page=True,
        )

        print(
            f"      ✅ {window}: "
            f"{len(window_data['html_rows'])} HTML rows, "
            f"{len(window_data['grid_rows'])} DataGrid rows"
        )

    # L10 is intentionally retained as the primary recent window for analysis.
    result["primary_recent_window"] = "L10"

    print("   ✅ wnba_volume_trends complete")

    return result


async def scrape_wnba_injury_splits(page, url):
    print("\n📄 Scraping wnba_injury_splits...")
    await navigate(page, url, 9000)

    data = await extract_structured_page(page)

    await page.screenshot(
        path="logs/wnba_injury_splits.png",
        full_page=True,
    )

    print(
        f"   ✅ wnba_injury_splits: "
        f"{len(data['html_rows'])} HTML rows, "
        f"{len(data['grid_rows'])} DataGrid rows"
    )

    return data


async def scrape_wnba_odds_discrepancies(page, url):
    print("\n📄 Scraping wnba_odds_discrepancies...")
    await navigate(page, url, 9000)

    data = await extract_structured_page(page)

    # Capture sportsbook/logo metadata because some book identities may
    # be represented visually rather than as plain text.
    images = page.locator("img")
    image_data = []

    for i in range(await images.count()):
        image = images.nth(i)

        try:
            image_data.append(
                {
                    "src": await image.get_attribute("src"),
                    "alt": await image.get_attribute("alt"),
                    "title": await image.get_attribute("title"),
                }
            )
        except Exception:
            pass

    data["images"] = image_data

    await page.screenshot(
        path="logs/wnba_odds_discrepancies.png",
        full_page=True,
    )

    print(
        f"   ✅ wnba_odds_discrepancies: "
        f"{len(data['html_rows'])} HTML rows, "
        f"{len(data['grid_rows'])} DataGrid rows"
    )

    return data


# ─────────────────────────────────────────────
# MLB MAIN RUNNER
# ─────────────────────────────────────────────

async def run_scraper():
    scrape_date = scrape_date_string()

    print(f"\n{'=' * 50}")
    print(f"⚾ MLB Picks Bot — Scraping {scrape_date}")
    print(f"{'=' * 50}\n")

    os.makedirs("logs", exist_ok=True)
    results = {}

    async with async_playwright() as p:
        headless_mode = (
            os.getenv("HEADLESS", "false").lower() == "true"
        )

        browser = await p.chromium.launch(
            headless=headless_mode
        )

        context = await browser.new_context(
            viewport={"width": 1400, "height": 900}
        )

        page = await context.new_page()

        try:
            await login(page)

            for name, url in MLB_URLS.items():
                try:
                    if name == "exit_velo":
                        results[name] = await scrape_exit_velo(
                            page,
                            url,
                        )

                    elif name == "projections":
                        results[name] = await scrape_projections(
                            page,
                            url,
                        )

                    else:
                        results[name] = await scrape_page(
                            page,
                            name,
                            url,
                        )

                    save_json(
                        scrape_date,
                        name,
                        results[name],
                    )

                except Exception as e:
                    print(
                        f"   ❌ Error scraping {name}: {e}"
                    )
                    results[name] = {}

            print(f"\n{'=' * 50}")
            print("✅ MLB Scraping complete!")
            print(f"{'=' * 50}\n")

        except Exception as e:
            print(f"\n❌ Fatal error: {e}")

            await page.screenshot(
                path="logs/fatal_error.png"
            )

            raise

        finally:
            await browser.close()

    return results


# ─────────────────────────────────────────────
# NBA MAIN RUNNER
# ─────────────────────────────────────────────

async def run_nba_scraper():
    """
    NBA now uses ONE browser/context/login for the full run instead of
    opening a new browser and logging in for each source.
    """
    scrape_date = scrape_date_string()

    print(f"\n{'=' * 50}")
    print(f"🏀 NBA Picks Bot — Scraping {scrape_date}")
    print(f"{'=' * 50}\n")

    os.makedirs("logs", exist_ok=True)
    results = {}

    async with async_playwright() as p:
        headless_mode = (
            os.getenv("HEADLESS", "false").lower() == "true"
        )

        browser = await p.chromium.launch(
            headless=headless_mode
        )

        context = await browser.new_context(
            viewport={"width": 1400, "height": 900}
        )

        page = await context.new_page()

        try:
            await login(page)

            # Research first
            results["nba_research"] = (
                await scrape_basketball_research(
                    page,
                    "nba",
                    scrape_date,
                )
            )

            nba_scrapers = {
                "nba_player_stats": scrape_nba_player_stats,
                "nba_def_matchups": scrape_nba_def_matchups,
                "nba_hit_rate": scrape_nba_hit_rate,
                "nba_injury_reports": scrape_nba_injury_reports,
                "nba_lineups": scrape_nba_lineups,
                "nba_team_stats": scrape_nba_team_stats,
            }

            for name, scraper_fn in nba_scrapers.items():
                try:
                    results[name] = await scraper_fn(
                        page,
                        NBA_URLS[name],
                    )

                    save_json(
                        scrape_date,
                        name,
                        results[name],
                    )

                except Exception as e:
                    print(
                        f"   ❌ Error scraping {name}: {e}"
                    )
                    results[name] = {}

            print(f"\n{'=' * 50}")
            print("✅ NBA Scraping complete!")
            print(f"{'=' * 50}\n")

        finally:
            await browser.close()

    return results


# ─────────────────────────────────────────────
# WNBA MAIN RUNNER
# ─────────────────────────────────────────────

async def run_wnba_scraper():
    """
    Production WNBA scraper with timeout protection.

    Included:
      - Research
      - Player Stats
      - Team Stats
      - Hit Rate Matrix
      - Injury Reports
      - Volume Trends: L3/L5/L10/L15
      - Injury Splits
      - Odds Discrepancies

    Every source has its own timeout so one bad PropFinder page
    cannot freeze the entire picks bot.
    """

    scrape_date = scrape_date_string()

    print(f"\n{'=' * 50}", flush=True)
    print(f"🏀 WNBA Picks Bot — Scraping {scrape_date}", flush=True)
    print(f"{'=' * 50}\n", flush=True)

    os.makedirs("logs", exist_ok=True)
    results = {}

    # Individual source limits
    LOGIN_TIMEOUT = 60

    SOURCE_TIMEOUTS = {
        "wnba_research": 90,
        "wnba_player_stats": 60,
        "wnba_team_stats": 60,
        "wnba_hit_rate": 60,
        "wnba_injury_reports": 60,

        # This page performs four window selections,
        # so give it a little more room.
        "wnba_volume_trends": 120,

        "wnba_injury_splits": 60,
        "wnba_odds_discrepancies": 60,
    }

    async def timed_scrape(name, coro):
        """
        Run one scraper with a hard timeout.

        Returns {} when the source times out or fails,
        allowing the rest of the WNBA pipeline to continue.
        """

        timeout_seconds = SOURCE_TIMEOUTS.get(name, 60)
        started = time.monotonic()

        print(
            f"\n⏱️ Starting {name} "
            f"(timeout: {timeout_seconds}s)...",
            flush=True,
        )

        try:
            result = await asyncio.wait_for(
                coro,
                timeout=timeout_seconds,
            )

            elapsed = time.monotonic() - started

            print(
                f"✅ {name} finished in {elapsed:.1f}s",
                flush=True,
            )

            return result

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - started

            print(
                f"⏰ {name} TIMED OUT after "
                f"{elapsed:.1f}s — skipping source.",
                flush=True,
            )

            return {}

        except Exception as e:
            elapsed = time.monotonic() - started

            print(
                f"❌ {name} failed after "
                f"{elapsed:.1f}s: {e}",
                flush=True,
            )

            return {}

    try:
        async with async_playwright() as p:

            headless_mode = (
                os.getenv("HEADLESS", "false").lower() == "true"
            )

            print(
                f"🌐 Launching Chromium "
                f"(headless={headless_mode})...",
                flush=True,
            )

            # Protect browser startup too.
            try:
                browser = await asyncio.wait_for(
                    p.chromium.launch(
                        headless=headless_mode,
                    ),
                    timeout=45,
                )

            except asyncio.TimeoutError:
                print(
                    "⏰ Chromium launch timed out after 45s. "
                    "Skipping WNBA PropFinder scrape.",
                    flush=True,
                )
                return results

            context = await browser.new_context(
                viewport={
                    "width": 1600,
                    "height": 1000,
                }
            )

            page = await context.new_page()

            # Playwright-level safety limits.
            page.set_default_timeout(30_000)
            page.set_default_navigation_timeout(45_000)

            try:

                # ──────────────────────────────────────
                # LOGIN
                # ──────────────────────────────────────

                print(
                    f"\n🔐 Logging into PropFinder "
                    f"(timeout: {LOGIN_TIMEOUT}s)...",
                    flush=True,
                )

                login_started = time.monotonic()

                try:
                    await asyncio.wait_for(
                        login(page),
                        timeout=LOGIN_TIMEOUT,
                    )

                    print(
                        f"✅ PropFinder login completed in "
                        f"{time.monotonic() - login_started:.1f}s",
                        flush=True,
                    )

                except asyncio.TimeoutError:

                    print(
                        f"⏰ PropFinder login timed out after "
                        f"{LOGIN_TIMEOUT}s. "
                        f"Skipping WNBA PropFinder.",
                        flush=True,
                    )

                    return results

                except Exception as e:

                    print(
                        f"❌ PropFinder login failed: {e}",
                        flush=True,
                    )

                    return results

                # ──────────────────────────────────────
                # 1. RESEARCH
                # ──────────────────────────────────────

                results["wnba_research"] = await timed_scrape(
                    "wnba_research",
                    scrape_wnba_research(
                        page,
                        scrape_date,
                    ),
                )

                if results["wnba_research"]:
                    save_json(
                        scrape_date,
                        "wnba_research",
                        results["wnba_research"],
                    )

                # ──────────────────────────────────────
                # REMAINING SOURCES
                # ──────────────────────────────────────

                wnba_scrapers = {
                    "wnba_player_stats":
                        scrape_wnba_player_stats,

                    "wnba_team_stats":
                        scrape_wnba_team_stats,

                    "wnba_hit_rate":
                        scrape_wnba_hit_rate,

                    "wnba_injury_reports":
                        scrape_wnba_injury_reports,

                    "wnba_volume_trends":
                        scrape_wnba_volume_trends,

                    "wnba_injury_splits":
                        scrape_wnba_injury_splits,

                    "wnba_odds_discrepancies":
                        scrape_wnba_odds_discrepancies,
                }

                for name, scraper_fn in wnba_scrapers.items():

                    results[name] = await timed_scrape(
                        name,
                        scraper_fn(
                            page,
                            WNBA_URLS[name],
                        ),
                    )

                    if results[name]:
                        try:
                            save_json(
                                scrape_date,
                                name,
                                results[name],
                            )
                        except Exception as e:
                            print(
                                f"⚠️ Could not save {name}: {e}",
                                flush=True,
                            )

                # ──────────────────────────────────────
                # SUMMARY
                # ──────────────────────────────────────

                summary = {
                    "date": scrape_date,
                    "league": "WNBA",
                    "sources": {},
                }

                for name, data in results.items():

                    if not isinstance(data, dict):
                        summary["sources"][name] = {
                            "status": "unknown",
                        }
                        continue

                    if not data:
                        summary["sources"][name] = {
                            "status": "failed_or_timed_out",
                        }
                        continue

                    if name == "wnba_volume_trends":

                        summary["sources"][name] = {
                            "status": "success",
                            "primary_recent_window": "L10",
                            "windows": {
                                window: {
                                    "html_rows": len(
                                        window_data.get(
                                            "html_rows",
                                            [],
                                        )
                                    ),
                                    "grid_rows": len(
                                        window_data.get(
                                            "grid_rows",
                                            [],
                                        )
                                    ),
                                    "selected":
                                        window_data.get(
                                            "selected",
                                            False,
                                        ),
                                }
                                for window, window_data
                                in data.get(
                                    "windows",
                                    {},
                                ).items()
                            },
                        }

                        continue

                    summary["sources"][name] = {
                        "status": "success",
                        "html_rows": len(
                            data.get(
                                "html_rows",
                                [],
                            )
                        ),
                        "grid_rows": len(
                            data.get(
                                "grid_rows",
                                [],
                            )
                        ),
                    }

                save_json(
                    scrape_date,
                    "wnba_summary",
                    summary,
                )

                print(
                    f"\n{'=' * 50}",
                    flush=True,
                )
                print(
                    "✅ WNBA scraping phase complete!",
                    flush=True,
                )
                print(
                    "⭐ Volume Trends primary window: L10",
                    flush=True,
                )
                print(
                    "ℹ️ Failed/timed-out sources were skipped.",
                    flush=True,
                )
                print(
                    f"{'=' * 50}\n",
                    flush=True,
                )

            finally:

                print(
                    "🧹 Closing WNBA browser...",
                    flush=True,
                )

                try:
                    await asyncio.wait_for(
                        browser.close(),
                        timeout=15,
                    )
                except Exception:
                    pass

    except Exception as e:

        print(
            f"\n⚠️ WNBA PropFinder scraper stopped: {e}",
            flush=True,
        )

        # IMPORTANT:
        # Do not raise here. Returning whatever was successfully
        # scraped allows CFB/NBA/email to continue.

    return results


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    command = (
        sys.argv[1].lower()
        if len(sys.argv) > 1
        else "mlb"
    )

    if command == "nba":
        asyncio.run(run_nba_scraper())

    elif command == "cfb":
        asyncio.run(run_cfb_scraper())

    elif command == "nfl":
        asyncio.run(run_nfl_scraper())

    elif command == "wnba":
        asyncio.run(run_wnba_scraper())

    elif command == "nrfi":
        asyncio.run(
            run_nrfi_scraper(
                scrape_date_string()
            )
        )

    elif command == "mlb":
        asyncio.run(run_scraper())

    else:
        print(
            "Unknown command. Use one of:\n"
            "  python3 scraper.py mlb\n"
            "  python3 scraper.py nba\n"
            "  python3 scraper.py cfb\n"
            "  python3 scraper.py nfl\n"
            "  python3 scraper.py wnba\n"
            "  python3 scraper.py nrfi"
        )
