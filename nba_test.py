import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://propfinder.app"

async def login(page):
    print("🔐 Logging in...")
    await page.goto(f"{BASE_URL}/login")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)
    await page.get_by_placeholder("your@email.com").fill(os.getenv("PROPFINDER_EMAIL"))
    await page.get_by_placeholder("••••••").fill(os.getenv("PROPFINDER_PASSWORD"))
    await page.locator('button[type="submit"]').click()
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(3000)
    print("✅ Logged in")

async def test_nba_research():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        await login(page)

        print("\n📄 Navigating to NBA Research...")
        await page.goto(f"{BASE_URL}/nba")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(8000)  # More time

        # Try scrolling to trigger lazy load
        await page.evaluate("window.scrollTo(0, 500)")
        await page.wait_for_timeout(3000)

        # Try clicking somewhere on the page to activate it
        try:
            await page.locator('body').click()
            await page.wait_for_timeout(3000)
        except:
            pass

        await page.screenshot(path="logs/nba_test_loaded.png")

        # Check what's actually on the page
        content = await page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll("tr"))
                .map(r => r.innerText.trim()).filter(Boolean);
            const fullText = document.body.innerText;

            // Also check for any loading indicators
            const loading = document.querySelector('[class*="loading"], [class*="spinner"]');
            const tables = document.querySelectorAll("table").length;
            const divCount = document.querySelectorAll("div").length;

            return { rows, fullText, tables, divCount,
                     isLoading: loading ? true : false };
        }''')

        print(f"✅ Rows found: {len(content['rows'])}")
        print(f"✅ Tables on page: {content['tables']}")
        print(f"✅ Divs on page: {content['divCount']}")
        print(f"✅ Is loading: {content['isLoading']}")
        print(f"✅ Full text length: {len(content['fullText'])} chars")
        print(f"\nFull text:")
        print(content['fullText'][:800])

        # Save raw data
        with open("logs/nba_research_test.json", "w") as f:
            json.dump(content, f, indent=2)
        print(f"\n💾 Saved to logs/nba_research_test.json")

        input("\nPress Enter to close browser...")
        await browser.close()

async def test_nba_def_matchups():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        await login(page)

        print("\n📄 Navigating to NBA Defensive Matchups...")
        await page.goto(f"{BASE_URL}/nba/cheatsheets/defensive-matchups")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(5000)

        await page.evaluate("window.scrollTo(0, 300)")
        await page.wait_for_timeout(2000)

        try:
            print("   🔧 Opening positions dropdown...")

            # Click the dropdown showing "PG" directly
            await page.get_by_text("PG", exact=True).click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path="logs/nba_def_dropdown_open.png")

            # Check what options are available
            options = await page.locator('[role="option"]').all()
            print(f"   Found {len(options)} options in dropdown")
            for opt in options:
                text = await opt.inner_text()
                print(f"   Option: '{text.strip()}'")

            # Click each missing position
            for pos in ['SG', 'PF', 'SF', 'C']:
                try:
                    await page.get_by_role("option", name=pos, exact=True).click()
                    await page.wait_for_timeout(400)
                    print(f"   ✅ Clicked {pos}")
                except Exception as e:
                    print(f"   ⚠️ {pos}: {e}")

            await page.keyboard.press("Escape")
            await page.wait_for_timeout(3000)

        except Exception as e:
            print(f"   ⚠️ Dropdown error: {e}")

        await page.screenshot(path="logs/nba_def_test.png")

        content = await page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll("tr"))
                .map(r => r.innerText.trim()).filter(Boolean);
            return { rows, fullText: document.body.innerText };
        }''')

        print(f"\n✅ Rows found: {len(content['rows'])}")
        print(f"✅ Full text length: {len(content['fullText'])} chars")
        print(f"\nFirst 800 chars:")
        print(content['fullText'][:800])

        with open("logs/nba_def_test.json", "w") as f:
            json.dump(content, f, indent=2)
        print(f"\n💾 Saved to logs/nba_def_test.json")

        input("\nPress Enter to close browser...")
        await browser.close()

async def test_nba_hit_rate():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        await login(page)

        print("\n📄 Navigating to NBA Hit Rate Matrix...")
        await page.goto(f"{BASE_URL}/nba/cheatsheets/hit-rate-matrix")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(5000)

        await page.evaluate("window.scrollTo(0, 300)")
        await page.wait_for_timeout(2000)

        # Step 1 — Set Game Count to 2025-26 Season
        try:
            print("   🔧 Setting Game Count to 2025-26 Season...")
            await page.get_by_text("Last 5 Games", exact=True).first.click()
            await page.wait_for_timeout(1000)

            options = await page.locator('[role="option"]').all()
            print(f"   Game Count options:")
            for opt in options:
                text = await opt.inner_text()
                print(f"     '{text.strip()}'")

            await page.get_by_role("option", name="2025-26 Season").click()
            await page.wait_for_timeout(2000)
            print("   ✅ Game Count set to 2025-26 Season")
        except Exception as e:
            print(f"   ⚠️ Game Count error: {e}")

        # Step 2 — Cycle through all categories
        categories = [
            'Points', 'Rebounds', 'Assists', 'Three Pointers',
            'Points + Rebounds', 'Points + Assists',
            'Rebounds + Assists', 'Pts + Reb + Ast'
        ]

        all_data = {}
        current_cat = 'Points'  # Track current category

        for cat in categories:
            try:
                print(f"\n   📊 Selecting category: {cat}")

                # Click whichever category is currently shown
                await page.get_by_text(current_cat, exact=True).first.click()
                await page.wait_for_timeout(1000)

                await page.get_by_role("option", name=cat, exact=True).click()
                await page.wait_for_timeout(2000)

                current_cat = cat  # Update tracker

                content = await page.evaluate('''() => {
                    return { fullText: document.body.innerText };
                }''')

                all_data[cat] = content['fullText']
                print(f"   ✅ {cat}: {len(content['fullText'])} chars")

            except Exception as e:
                print(f"   ⚠️ {cat} error: {e}")
                # Try reloading page and resetting if stuck
                await page.goto(f"{BASE_URL}/nba/cheatsheets/hit-rate-matrix")
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(4000)
                try:
                    await page.get_by_text("Last 5 Games", exact=True).first.click()
                    await page.wait_for_timeout(500)
                    await page.get_by_role("option", name="2025-26 Season").click()
                    await page.wait_for_timeout(2000)
                except:
                    pass
                current_cat = 'Points'
                all_data[cat] = ''

        await page.screenshot(path="logs/nba_hit_rate_test.png")

        with open("logs/nba_hit_rate_test.json", "w") as f:
            json.dump(all_data, f, indent=2)
        print(f"\n💾 Saved to logs/nba_hit_rate_test.json")
        print(f"✅ Categories collected: {len(all_data)}")

        input("\nPress Enter to close browser...")
        await browser.close()

async def test_nba_simple_pages():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        await login(page)

        for name, url in [
            ("injury_reports", f"{BASE_URL}/nba/cheatsheets/injury-reports"),
            ("lineups", f"{BASE_URL}/nba/cheatsheets/lineups")
        ]:
            print(f"\n📄 Testing {name}...")
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(5000)

            if name == "lineups":
                # Use ALL TEAMS tab — more reliable than TODAY'S GAMES
                try:
                    await page.get_by_text("ALL TEAMS").click()
                    await page.wait_for_timeout(3000)
                    print("   ✅ Clicked ALL TEAMS")
                except:
                    pass

                # Wait for actual content to load
                try:
                    await page.wait_for_selector("text=Today's Lineup", timeout=15000)
                    print("   ✅ Lineup content detected")
                except:
                    print("   ⚠️ Still waiting...")
                    await page.wait_for_timeout(5000)

                # Scroll through page to trigger lazy loading
                for scroll_pos in [500, 1000, 1500, 2000, 2500]:
                    await page.evaluate(f"window.scrollTo(0, {scroll_pos})")
                    await page.wait_for_timeout(800)

                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(1000)

                dom_check = await page.evaluate('''() => {
                    const allText = document.body.innerText;
                    const divCount = document.querySelectorAll("div").length;
                    return { allText, divCount };
                }''')

                print(f"   Div count: {dom_check['divCount']}")
                print(f"   Text length: {len(dom_check['allText'])}")
                print(f"   First 800 chars:")
                print(dom_check['allText'][:800])

                with open("logs/nba_lineups_test.json", "w") as f:
                    json.dump({"fullText": dom_check['allText']}, f, indent=2)

            await page.screenshot(path=f"logs/nba_{name}_test.png")

        input("\nPress Enter to close browser...")
        await browser.close()

async def test_player_stats_summary():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        await login(page)

        print("\n📄 Navigating to Player Stats Summary...")
        await page.goto(f"{BASE_URL}/nba/cheatsheets/player-stats-summary")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(5000)
        await page.evaluate("window.scrollTo(0, 500)")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="logs/nba_player_stats_test.png")

        content = await page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll("tr"))
                .map(r => r.innerText.trim()).filter(Boolean);
            return { rows, fullText: document.body.innerText };
        }''')

        print(f"✅ Rows found: {len(content['rows'])}")
        print(f"✅ Text length: {len(content['fullText'])} chars")
        print(content['fullText'][:600])

        with open("logs/nba_player_stats_test.json", "w") as f:
            json.dump(content, f, indent=2)

        input("\nPress Enter to close browser...")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_player_stats_summary())


"""if __name__ == "__main__":
    asyncio.run(test_nba_simple_pages())"""


"""if __name__ == "__main__":
    asyncio.run(test_nba_hit_rate())"""


"""if __name__ == "__main__":
    asyncio.run(test_nba_def_matchups())"""

"""if __name__ == "__main__":
    asyncio.run(test_nba_research())"""