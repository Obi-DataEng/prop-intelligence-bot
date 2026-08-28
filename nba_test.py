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
        await page.wait_for_timeout(8000)

        print("   📜 Scrolling MuiDataGrid-virtualScroller...")
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
                print("   ❌ Scroller not found")
                break

            new_rows = set(result['rows'])
            before = len(all_rows)
            all_rows.update(new_rows)
            after = len(all_rows)

            print(f"   Scroll {scroll_pos}px / {result['height']}px: "
                  f"{len(new_rows)} visible, {after} total unique (+{after - before})")

            if after == last_count:
                no_change_count += 1
            else:
                no_change_count = 0
                last_count = after

            if no_change_count >= 6:
                print("   ✅ Done — no new rows")
                break

            scroll_pos += scroll_step
            if scroll_pos > result['height']:
                print("   ✅ Reached end of scroller")
                break

            await page.wait_for_timeout(200)

        print(f"\n   📊 Total unique rows captured: {len(all_rows)}")
        print(f"\n   📝 Sample rows:")
        sample = [r for r in all_rows if len(r) > 30][:15]
        for row in sample:
            print(f"      {row[:150]}")

        with open("logs/nba_research_test.json", "w") as f:
            json.dump({
                'total_rows': len(all_rows),
                'rows': list(all_rows)
            }, f, indent=2)

        print(f"\n💾 Saved to logs/nba_research_test.json")
        await page.screenshot(path="logs/nba_research_test.png")
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
            await page.get_by_text("PG", exact=True).click()
            await page.wait_for_timeout(1500)

            options = await page.locator('[role="option"]').all()
            print(f"   Found {len(options)} options in dropdown")
            for opt in options:
                text = await opt.inner_text()
                print(f"   Option: '{text.strip()}'")

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

        categories = [
            'Points', 'Rebounds', 'Assists', 'Three Pointers',
            'Points + Rebounds', 'Points + Assists',
            'Rebounds + Assists', 'Pts + Reb + Ast'
        ]

        all_data = {}
        current_cat = 'Points'

        for cat in categories:
            try:
                print(f"\n   📊 Selecting category: {cat}")
                await page.get_by_text(current_cat, exact=True).first.click()
                await page.wait_for_timeout(1000)
                await page.get_by_role("option", name=cat, exact=True).click()
                await page.wait_for_timeout(2000)
                current_cat = cat

                content = await page.evaluate('''() => {
                    return { fullText: document.body.innerText };
                }''')

                all_data[cat] = content['fullText']
                print(f"   ✅ {cat}: {len(content['fullText'])} chars")

            except Exception as e:
                print(f"   ⚠️ {cat} error: {e}")
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
        print(f"\n📊 Sample of Points data:")
        print(all_data.get('Points', '')[:1000])

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
                try:
                    await page.get_by_text("ALL TEAMS").click()
                    await page.wait_for_timeout(3000)
                    print("   ✅ Clicked ALL TEAMS")
                except:
                    pass

                try:
                    await page.wait_for_selector("text=Today's Lineup", timeout=15000)
                    print("   ✅ Lineup content detected")
                except:
                    print("   ⚠️ Still waiting...")
                    await page.wait_for_timeout(5000)

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
    asyncio.run(test_nba_research())