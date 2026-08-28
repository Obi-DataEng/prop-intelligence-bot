import asyncio
import json
import os
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
    Production WNBA V1.

    Included:
      - Research
      - Player Stats
      - Team Stats
      - Hit Rate Matrix
      - Injury Reports
      - Volume Trends: L3/L5/L10/L15
      - Injury Splits
      - Odds Discrepancies

    Defensive Matchups and Lineups are intentionally excluded from V1
    because PropFinder's WNBA feeds were not reliably returning data.
    """
    scrape_date = scrape_date_string()

    print(f"\n{'=' * 50}")
    print(f"🏀 WNBA Picks Bot — Scraping {scrape_date}")
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
            viewport={"width": 1600, "height": 1000}
        )

        page = await context.new_page()

        try:
            # One login for the entire WNBA run.
            await login(page)

            # 1. Research
            try:
                results["wnba_research"] = (
                    await scrape_wnba_research(
                        page,
                        scrape_date,
                    )
                )
            except Exception as e:
                print(
                    f"   ❌ Error scraping wnba_research: {e}"
                )
                results["wnba_research"] = {}

            # 2. Player Stats
            # 3. Team Stats
            # 4. Hit Rate Matrix
            # 5. Injury Reports
            # 6. Volume Trends
            # 7. Injury Splits
            # 8. Odds Discrepancies
            wnba_scrapers = {
                "wnba_player_stats": scrape_wnba_player_stats,
                "wnba_team_stats": scrape_wnba_team_stats,
                "wnba_hit_rate": scrape_wnba_hit_rate,
                "wnba_injury_reports": scrape_wnba_injury_reports,
                "wnba_volume_trends": scrape_wnba_volume_trends,
                "wnba_injury_splits": scrape_wnba_injury_splits,
                "wnba_odds_discrepancies": scrape_wnba_odds_discrepancies,
            }

            for name, scraper_fn in wnba_scrapers.items():
                try:
                    results[name] = await scraper_fn(
                        page,
                        WNBA_URLS[name],
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

                    try:
                        await page.screenshot(
                            path=f"logs/{name}_error.png",
                            full_page=True,
                        )
                    except Exception:
                        pass

            summary = {
                "date": scrape_date,
                "league": "WNBA",
                "sources": {},
            }

            for name, data in results.items():
                if not isinstance(data, dict):
                    summary["sources"][name] = {
                        "status": "unknown"
                    }
                    continue

                if name == "wnba_research":
                    summary["sources"][name] = {
                        "rows": data.get("total", 0)
                    }
                    continue

                if name == "wnba_volume_trends":
                    summary["sources"][name] = {
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
                                "selected": window_data.get(
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
                    "html_rows": len(
                        data.get("html_rows", [])
                    ),
                    "grid_rows": len(
                        data.get("grid_rows", [])
                    ),
                }

            save_json(
                scrape_date,
                "wnba_summary",
                summary,
            )

            print(f"\n{'=' * 50}")
            print("✅ WNBA Scraping complete!")
            print("⭐ Volume Trends primary window: L10")
            print(
                "ℹ️ WNBA Defensive Matchups + Lineups "
                "remain disabled for V1"
            )
            print(f"{'=' * 50}\n")

        except Exception as e:
            print(f"\n❌ WNBA fatal error: {e}")

            try:
                await page.screenshot(
                    path="logs/wnba_fatal_error.png",
                    full_page=True,
                )
            except Exception:
                pass

            raise

        finally:
            await browser.close()

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
            "  python3 scraper.py wnba\n"
            "  python3 scraper.py nrfi"
        )
