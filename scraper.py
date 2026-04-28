import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://propfinder.app"

MLB_URLS = {
    "hr_matchups":     f"{BASE_URL}/mlb/cheatsheets",
    "exit_velo":       f"{BASE_URL}/mlb/cheatsheets/exit-velo",
    "pitcher_summary": f"{BASE_URL}/mlb/cheatsheets/pitcher-summary",
    "park_factors":    f"{BASE_URL}/mlb/cheatsheets/park-factors",
    "weather":         f"{BASE_URL}/mlb/cheatsheets/ballpark-weather",
    "projections":     f"{BASE_URL}/projections/mlb",
}

NBA_URLS = {
    "nba_player_stats": f"{BASE_URL}/nba/cheatsheets/player-stats-summary",
    "nba_team_stats": f"{BASE_URL}/nba/cheatsheets/team-stats",
    "nba_def_matchups":   f"{BASE_URL}/nba/cheatsheets/defensive-matchups",
    "nba_hit_rate":       f"{BASE_URL}/nba/cheatsheets/hit-rate-matrix",
    "nba_injury_reports": f"{BASE_URL}/nba/cheatsheets/injury-reports",
    "nba_lineups":        f"{BASE_URL}/nba/cheatsheets/lineups",
}

# ─────────────────────────────────────────────
# SHARED
# ─────────────────────────────────────────────

async def login(page):
    print("🔐 Logging into PropFinder...")
    await page.goto(f"{BASE_URL}/login")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)
    await page.screenshot(path="logs/login_page.png")
    try:
        await page.get_by_placeholder("your@email.com").fill(os.getenv("PROPFINDER_EMAIL"))
        await page.get_by_placeholder("••••••").fill(os.getenv("PROPFINDER_PASSWORD"))
        await page.locator('button[type="submit"]').click()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="logs/login_result.png")
        print("✅ Login attempted")
    except Exception as e:
        print(f"❌ Login error: {e}")
        raise e

# ─────────────────────────────────────────────
# MLB SCRAPERS
# ─────────────────────────────────────────────

async def scrape_page(page, name, url):
    print(f"\n📄 Scraping {name}...")
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(3000)
    await page.screenshot(path=f"logs/{name}.png")
    content = await page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll("tr")).map(r => r.innerText.trim()).filter(Boolean);
        const cells = Array.from(document.querySelectorAll("td, th")).map(c => c.innerText.trim()).filter(Boolean);
        const fullText = document.body.innerText;
        return { rows, cells, fullText };
    }''')
    print(f"   ✅ {name}: {len(content['rows'])} rows, {len(content['cells'])} cells found")
    return content

async def scrape_exit_velo(page, url):
    print(f"\n📄 Scraping exit_velo...")
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)
    try:
        await page.get_by_role("button", name="SEARCH").click()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(3000)
        print("   ✅ Search clicked")
    except Exception as e:
        print(f"   ⚠️ Could not click search: {e}")
    await page.screenshot(path="logs/exit_velo.png")
    content = await page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll("tr")).map(r => r.innerText.trim()).filter(Boolean);
        const cells = Array.from(document.querySelectorAll("td, th")).map(c => c.innerText.trim()).filter(Boolean);
        const fullText = document.body.innerText;
        return { rows, cells, fullText };
    }''')
    print(f"   ✅ exit_velo: {len(content['rows'])} rows, {len(content['cells'])} cells found")
    return content

async def scrape_projections(page, url):
    print(f"\n📄 Scraping projections...")
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(3000)
    try:
        await page.get_by_text("CONSENSUS").click()
        await page.wait_for_timeout(2000)
        print("   ✅ Switched to CONSENSUS tab")
    except Exception as e:
        print(f"   ⚠️ Could not click CONSENSUS: {e}")
    await page.screenshot(path="logs/projections.png")
    content = await page.evaluate('''() => {
        const fullText = document.body.innerText;
        return { rows: [], cells: [], fullText };
    }''')
    game_count = content['fullText'].count('Proj Runs') // 2
    print(f"   ✅ projections: {game_count} games found")
    return content

# ─────────────────────────────────────────────
# NBA SCRAPERS
# ─────────────────────────────────────────────

async def scrape_nba_team_stats(page, url):
    print(f"\n📄 Scraping nba_team_stats...")
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(5000)
    await page.evaluate("window.scrollTo(0, 300)")
    await page.wait_for_timeout(2000)
    await page.screenshot(path="logs/nba_team_stats.png")

    content = await page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll("tr"))
            .map(r => r.innerText.trim()).filter(Boolean);
        return { rows, fullText: document.body.innerText };
    }''')
    print(f"   ✅ nba_team_stats: {len(content['rows'])} rows")
    return content

async def scrape_nba_player_stats(page, url):
    print(f"\n📄 Scraping nba_player_stats...")
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(5000)
    await page.evaluate("window.scrollTo(0, 500)")
    await page.wait_for_timeout(3000)
    await page.screenshot(path="logs/nba_player_stats.png")

    content = await page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll("tr"))
            .map(r => r.innerText.trim()).filter(Boolean);
        return { rows, fullText: document.body.innerText };
    }''')
    print(f"   ✅ nba_player_stats: {len(content['rows'])} rows")
    return content

async def scrape_nba_research(page, url):
    print(f"\n📄 Scraping nba_research...")
    await page.goto(url)
    await page.wait_for_load_state("networkidle")

    # Wait for actual table rows to appear
    try:
        await page.wait_for_selector("tr", timeout=50000)  # 30 seconds
        print("   ✅ Table rows detected")
    except:
        print("   ⚠️ Table timeout — trying scroll")

    await page.evaluate("window.scrollTo(0, 500)")
    await page.wait_for_timeout(10000)  # 5 seconds after scroll
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(10000)

    over_content = await page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll("tr"))
            .map(r => r.innerText.trim()).filter(Boolean);
        return { rows, fullText: document.body.innerText };
    }''')
    print(f"   ✅ OVER: {len(over_content['rows'])} rows")

    try:
        await page.locator('button:has-text("UNDER")').first.click()
        await page.wait_for_timeout(3000)
        under_content = await page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll("tr"))
                .map(r => r.innerText.trim()).filter(Boolean);
            return { rows, fullText: document.body.innerText };
        }''')
        print(f"   ✅ UNDER: {len(under_content['rows'])} rows")
    except Exception as e:
        print(f"   ⚠️ UNDER error: {e}")
        under_content = {'rows': [], 'fullText': ''}

    await page.screenshot(path="logs/nba_research.png")
    total = len(over_content['rows']) + len(under_content['rows'])
    print(f"   ✅ nba_research total: {total} rows")
    return {'over': over_content, 'under': under_content}

async def scrape_nba_def_matchups(page, url):
    print(f"\n📄 Scraping nba_def_matchups...")
    await page.goto(url)
    await page.wait_for_load_state("networkidle")

    # Wait for actual table rows to appear
    try:
        await page.wait_for_selector("tr", timeout=50000)  # 30 seconds
        print("   ✅ Table rows detected")
    except:
        print("   ⚠️ Table timeout — trying scroll")

    await page.evaluate("window.scrollTo(0, 300)")
    await page.wait_for_timeout(10000)  # 5 seconds after scroll

    try:
        await page.locator('.MuiChip-label').get_by_text("PG", exact=True).first.click()
        await page.wait_for_timeout(1500)

        for pos in ['SG', 'PF', 'SF', 'C']:
            try:
                await page.get_by_role("option", name=pos, exact=True).click()
                await page.wait_for_timeout(400)
                print(f"   ✅ Selected {pos}")
            except Exception as e:
                print(f"   ⚠️ {pos}: {e}")

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(3000)

    except Exception as e:
        print(f"   ⚠️ Position dropdown error: {e}")

    await page.screenshot(path="logs/nba_def_matchups.png")
    content = await page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll("tr"))
            .map(r => r.innerText.trim()).filter(Boolean);
        return { rows, fullText: document.body.innerText };
    }''')
    print(f"   ✅ nba_def_matchups: {len(content['rows'])} rows")
    return content

async def scrape_nba_hit_rate(page, url):
    print(f"\n📄 Scraping nba_hit_rate...")
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(5000)
    await page.evaluate("window.scrollTo(0, 300)")
    await page.wait_for_timeout(2000)

    # Set Game Count to 2025-26 Season
    try:
        await page.get_by_text("Last 5 Games", exact=True).first.click()
        await page.wait_for_timeout(1000)
        await page.get_by_role("option", name="2025-26 Season").click()
        await page.wait_for_timeout(2000)
        print("   ✅ Game Count set to 2025-26 Season")
    except Exception as e:
        print(f"   ⚠️ Game Count error: {e}")

    # Cycle through all categories
    categories = [
        'Points', 'Rebounds', 'Assists', 'Three Pointers',
        'Points + Rebounds', 'Points + Assists',
        'Rebounds + Assists', 'Pts + Reb + Ast'
    ]

    all_data = {}
    current_cat = 'Points'

    for cat in categories:
        try:
            await page.get_by_text(current_cat, exact=True).first.click()
            await page.wait_for_timeout(1500)  # Increased from 1000
            await page.get_by_role("option", name=cat, exact=True).click()
            await page.wait_for_timeout(2500)  # Increased from 2000
            current_cat = cat

            content = await page.evaluate('''() => {
                return { fullText: document.body.innerText };
            }''')
            all_data[cat] = content['fullText']
            print(f"   ✅ {cat}: {len(content['fullText'])} chars")

        except Exception as e:
            print(f"   ⚠️ {cat} error: {e}")
            all_data[cat] = ''
            current_cat = 'Points'

    await page.screenshot(path="logs/nba_hit_rate.png")
    print(f"   ✅ nba_hit_rate: {len(all_data)} categories")
    return all_data

async def scrape_nba_injury_reports(page, url):
    print(f"\n📄 Scraping nba_injury_reports...")
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(5000)
    await page.evaluate("window.scrollTo(0, 300)")
    await page.wait_for_timeout(2000)
    await page.screenshot(path="logs/nba_injury_reports.png")

    content = await page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll("tr"))
            .map(r => r.innerText.trim()).filter(Boolean);
        return { rows, fullText: document.body.innerText };
    }''')
    print(f"   ✅ nba_injury_reports: {len(content['rows'])} rows")
    return content

async def scrape_nba_research(page, scrape_date):
    """Scrape NBA Research tab - all today's props with hit rates"""
    print("\n📄 Scraping nba_research...")
    
    try:
        await page.goto(f"{BASE_URL}/nba")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(8000)

        all_rows = set()
        scroll_pos = 0
        scroll_step = 400
        no_change_count = 0
        last_count = 0

        while True:
            result = await page.evaluate(f'''() => {{
                const scroller = document.querySelector(
                    ".MuiDataGrid-virtualScroller"
                );
                if (!scroller) return {{ rows: [], height: 0 }};

                scroller.scrollTop = {scroll_pos};

                return new Promise(resolve => {{
                    setTimeout(() => {{
                        const rows = Array.from(
                            document.querySelectorAll(".MuiDataGrid-row")
                        ).map(row => {{
                            const cells = Array.from(
                                row.querySelectorAll(".MuiDataGrid-cell")
                            ).map(cell => cell.innerText.trim());
                            return cells.join(" | ");
                        }}).filter(r => r.length > 10);

                        resolve({{
                            rows,
                            height: scroller.scrollHeight
                        }});
                    }}, 600);
                }});
            }}''')

            if not result['height']:
                print("   ⚠️ Scroller not found")
                break

            new_rows = set(result['rows'])
            before = len(all_rows)
            all_rows.update(new_rows)
            after = len(all_rows)

            if after != last_count:
                no_change_count = 0
                last_count = after
            else:
                no_change_count += 1

            if no_change_count >= 6:
                break

            scroll_pos += scroll_step
            if scroll_pos > result['height']:
                break

            await page.wait_for_timeout(200)

        # Clean up rows — remove malformed ones
        clean_rows = []
        for row in all_rows:
            # Must contain a player-like pattern and a prop
            if ' | ' in row and len(row) > 30:
                # Collapse internal newlines
                cleaned = ' '.join(row.split())
                clean_rows.append(cleaned)

        print(f"   ✅ nba_research: {len(clean_rows)} rows")

        data = {
            'rows': clean_rows,
            'total': len(clean_rows)
        }

        filepath = f"logs/{scrape_date}_nba_research.json"
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

        return data

    except Exception as e:
        print(f"   ❌ nba_research scrape failed: {e}")
        return {'rows': [], 'total': 0}

async def scrape_nba_lineups(page, url):
    print(f"\n📄 Scraping nba_lineups...")
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(5000)

    try:
        await page.get_by_text("ALL TEAMS").click()
        await page.wait_for_timeout(3000)
        print("   ✅ Clicked ALL TEAMS")
    except Exception as e:
        print(f"   ⚠️ ALL TEAMS click error: {e}")

    # Scroll to trigger lazy loading
    for scroll_pos in [500, 1000, 1500, 2000, 2500]:
        await page.evaluate(f"window.scrollTo(0, {scroll_pos})")
        await page.wait_for_timeout(800)

    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(1000)
    await page.screenshot(path="logs/nba_lineups.png")

    content = await page.evaluate('''() => {
        return { fullText: document.body.innerText };
    }''')
    print(f"   ✅ nba_lineups: {len(content['fullText'])} chars")
    return content

# ─────────────────────────────────────────────
# MLB MAIN RUNNER
# ─────────────────────────────────────────────

async def run_scraper():
    scrape_date = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*50}")
    print(f"⚾ MLB Picks Bot — Scraping {scrape_date}")
    print(f"{'='*50}\n")
    os.makedirs("logs", exist_ok=True)
    results = {}

    async with async_playwright() as p:
        headless_mode = os.getenv("HEADLESS", "false").lower() == "true"
        browser = await p.chromium.launch(headless=headless_mode)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await login(page)
            current_url = page.url
            print(f"📍 Current URL: {current_url}")
            if "login" in current_url:
                print("⚠️  Still on login page — check credentials")
                await browser.close()
                return
            print("✅ Successfully logged in!")

            for name, url in MLB_URLS.items():
                try:
                    if name == "exit_velo":
                        results[name] = await scrape_exit_velo(page, url)
                    elif name == "projections":
                        results[name] = await scrape_projections(page, url)
                    else:
                        results[name] = await scrape_page(page, name, url)
                    with open(f"logs/{scrape_date}_{name}.json", "w") as f:
                        json.dump(results[name], f, indent=2)
                except Exception as e:
                    print(f"   ❌ Error scraping {name}: {e}")

            print(f"\n{'='*50}")
            print(f"✅ Scraping complete!")
            print(f"📁 Raw data saved to /logs")
            print(f"{'='*50}\n")

        except Exception as e:
            print(f"\n❌ Fatal error: {e}")
            await page.screenshot(path="logs/fatal_error.png")
            raise e
        finally:
            await browser.close()

    return results

# ─────────────────────────────────────────────
# NBA MAIN RUNNER
# ─────────────────────────────────────────────

async def run_nba_scraper():
    scrape_date = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*50}")
    print(f"🏀 NBA Picks Bot — Scraping {scrape_date}")
    print(f"{'='*50}\n")
    os.makedirs("logs", exist_ok=True)
    results = {}

    nba_scrapers = {
    "nba_player_stats":   scrape_nba_player_stats,
    "nba_def_matchups":   scrape_nba_def_matchups,
    "nba_hit_rate":       scrape_nba_hit_rate,
    "nba_injury_reports": scrape_nba_injury_reports,
    "nba_lineups":        scrape_nba_lineups,
    "nba_team_stats":     scrape_nba_team_stats,
}

    headless_mode = os.getenv("HEADLESS", "false").lower() == "true"

    # Run each scraper in its own browser session
    for name, scraper_fn in nba_scrapers.items():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless_mode)
            context = await browser.new_context(viewport={"width": 1400, "height": 900})
            page = await context.new_page()
            try:
                await login(page)
                results[name] = await scraper_fn(page, NBA_URLS[name])
                with open(f"logs/{scrape_date}_{name}.json", "w") as f:
                    json.dump(results[name], f, indent=2)
            except Exception as e:
                print(f"   ❌ Error scraping {name}: {e}")
                results[name] = {}
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass

    print(f"\n{'='*50}")
    print(f"✅ NBA Scraping complete!")
    print(f"📁 Raw data saved to /logs")
    print(f"{'='*50}\n")

    return results

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "nba":
        asyncio.run(run_nba_scraper())
    else:
        asyncio.run(run_scraper())