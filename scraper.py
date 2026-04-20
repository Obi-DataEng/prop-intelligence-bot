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

if __name__ == "__main__":
    asyncio.run(run_scraper())