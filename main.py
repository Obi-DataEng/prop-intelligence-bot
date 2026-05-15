import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


async def run_all():
    scrape_date = datetime.now().strftime("%Y-%m-%d")
    start_time = datetime.now()

    print(f"\n{'='*60}")
    print(f"🤖 MLB + NBA PICKS BOT — {scrape_date}")
    print(f"⏰ Started at {start_time.strftime('%I:%M %p')}")
    print(f"{'='*60}\n")

    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    from grader import init_db
    init_db()

    # ── STEP 1: SCRAPE PROPFINDER (MLB) ──────────────────────────
    print(f"📡 STEP 1 — Scraping PropFinder (MLB)...")
    try:
        from scraper import run_scraper
        await run_scraper()
        print(f"✅ Step 1 complete\n")
    except Exception as e:
        print(f"❌ Scraper failed: {e}")
        print(f"⚠️  Continuing without PropFinder data...\n")

    # ── STEP 1.5: SCRAPE NRFI DATA ────────────────────────────────
    print(f"🎰 STEP 1.5 — Scraping NRFI/YRFI data...")
    nrfi_data = None
    try:
        from scraper import run_nrfi_scraper
        nrfi_data = await run_nrfi_scraper(scrape_date)
        total_matchups = len(nrfi_data.get('matchups', []))
        print(f"✅ Step 1.5 complete — {total_matchups} matchup cards\n")
    except Exception as e:
        print(f"⚠️ NRFI scraper failed (skipping): {e}\n")

    # ── STEP 2: FETCH MLB ODDS ────────────────────────────────────
    print(f"💰 STEP 2 — Fetching MLB odds from 4 books...")
    odds_data = {}
    try:
        from odds_fetcher import fetch_all_odds
        fetch_all_odds()
        odds_file = f"logs/{scrape_date}_odds.json"
        if os.path.exists(odds_file):
            with open(odds_file, 'r') as f:
                odds_data = json.load(f)
        print(f"✅ Step 2 complete\n")
    except Exception as e:
        print(f"❌ Odds fetcher failed: {e}")
        print(f"⚠️  Continuing without fresh odds...\n")

    # ── STEP 2.5: FETCH MLB NEWS ──────────────────────────────────
    print(f"📰 STEP 2.5 — Fetching MLB news...")
    try:
        from news_fetcher import fetch_mlb_news
        fetch_mlb_news(odds_data.get('games', []), scrape_date)
        print(f"✅ Step 2.5 complete\n")
    except Exception as e:
        print(f"⚠️ MLB news failed (skipping): {e}\n")

    # ── STEP 3: GENERATE MLB PICKS ────────────────────────────────
    print(f"🧠 STEP 3 — Generating MLB picks with Claude...")
    picks = None
    try:
        from parser import run_parser
        from analyzer import load_odds, analyze_and_generate_picks

        raw_data = {}
        for tab in ['hr_matchups', 'exit_velo', 'pitcher_summary',
                    'park_factors', 'weather', 'projections']:
            filepath = f"logs/{scrape_date}_{tab}.json"
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    raw_data[tab] = json.load(f)
                print(f"   📂 Loaded {tab}")
            else:
                print(f"   ⚠️  Missing {filepath}")

        parsed = run_parser(raw_data, scrape_date)
        odds_data = load_odds(scrape_date)
        picks = analyze_and_generate_picks(parsed, odds_data, scrape_date)

        if picks:
            output_file = f"logs/{scrape_date}_picks.json"
            with open(output_file, 'w') as f:
                json.dump(picks, f, indent=2)
            pick_count = len(picks.get('top_picks', []))
            print(f"✅ Step 3 complete — {pick_count} picks saved\n")
        else:
            print(f"❌ No picks generated\n")

    except Exception as e:
        print(f"❌ Analyzer failed: {e}")
        import traceback; traceback.print_exc()

    # ── STEP 3.2: GENERATE NRFI PICKS ────────────────────────────
    print(f"🎰 STEP 3.2 — Generating NRFI picks with Claude...")
    nrfi_picks = None
    try:
        if not nrfi_data:
            nrfi_file = f"logs/{scrape_date}_nrfi.json"
            if os.path.exists(nrfi_file):
                with open(nrfi_file, 'r') as f:
                    nrfi_data = json.load(f)

        if nrfi_data:
            import anthropic
            from analyzer import generate_nrfi_picks
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            nrfi_picks = generate_nrfi_picks(nrfi_data, scrape_date, client)

            if picks is not None:
                picks['nrfi_picks'] = nrfi_picks or []
                output_file = f"logs/{scrape_date}_picks.json"
                with open(output_file, 'w') as f:
                    json.dump(picks, f, indent=2)

            print(f"✅ Step 3.2 complete — {len(nrfi_picks) if nrfi_picks else 0} NRFI pick(s)\n")
        else:
            print(f"⚠️ No NRFI data available, skipping\n")

    except Exception as e:
        print(f"⚠️ NRFI analyzer failed (skipping): {e}\n")
        import traceback; traceback.print_exc()

    # ── STEP 3.5: GRADE YESTERDAY'S PICKS ────────────────────────
    print(f"📊 STEP 3.5 — Grading yesterday's picks...")
    graded_summary = None
    cumulative = None
    try:
        from grader import run_grader
        graded_summary, cumulative = run_grader()
        print(f"✅ Step 3.5 complete\n")
    except Exception as e:
        print(f"⚠️ Grader failed (skipping): {e}\n")

    # ── STEP 3.6: NBA SCRAPE ──────────────────────────────────────
    print(f"🏀 STEP 3.6 — Scraping NBA data...")
    try:
        from scraper import run_nba_scraper
        await run_nba_scraper()
        print(f"✅ Step 3.6 complete\n")
    except Exception as e:
        print(f"⚠️ NBA scraper failed (skipping): {e}\n")

    # ── STEP 3.65: NBA RESEARCH PAGE ─────────────────────────────
    print(f"🏀 STEP 3.65 — Scraping NBA Research page...")
    try:
        import scraper as scraper_module
        from playwright.async_api import async_playwright

        headless = os.getenv("HEADLESS", "false").lower() == "true"

        async def run_research():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless)
                context = await browser.new_context()
                page = await context.new_page()
                await scraper_module.login(page)
                result = await scraper_module.scrape_nba_research(page, scrape_date)
                await browser.close()
                return result

        research_data = await run_research()
        print(f"✅ Step 3.65 complete — {research_data['total']} research rows\n")
    except Exception as e:
        print(f"⚠️ Research scrape failed (skipping): {e}\n")

    # ── STEP 3.7: NBA ODDS ────────────────────────────────────────
    print(f"🏀 STEP 3.7 — Fetching NBA odds...")
    nba_odds = None
    nba_odds_data = {}
    try:
        from odds_fetcher import fetch_nba_odds
        nba_odds = fetch_nba_odds()

        nba_odds_file = f"logs/{scrape_date}_nba_odds.json"
        if os.path.exists(nba_odds_file):
            with open(nba_odds_file, 'r') as f:
                nba_odds_data = json.load(f)

        print(f"✅ Step 3.7 complete\n")
    except Exception as e:
        print(f"⚠️ NBA odds failed (skipping): {e}\n")

    # ── STEP 3.75: FETCH NBA NEWS ─────────────────────────────────
    print(f"📰 STEP 3.75 — Fetching NBA news...")
    try:
        from news_fetcher import fetch_nba_news
        fetch_nba_news(nba_odds_data.get('games', []), scrape_date)
        print(f"✅ Step 3.75 complete\n")
    except Exception as e:
        print(f"⚠️ NBA news failed (skipping): {e}\n")

    # ── STEP 3.8: NBA PICKS ───────────────────────────────────────
    print(f"🏀 STEP 3.8 — Generating NBA picks...")
    nba_picks = None
    try:
        from nba_analyzer import run_nba_analyzer
        nba_picks = run_nba_analyzer(scrape_date, nba_odds)
        nba_count = len(nba_picks.get('top_picks', [])) if nba_picks else 0
        print(f"✅ Step 3.8 complete — {nba_count} NBA pick(s)\n")
    except Exception as e:
        print(f"⚠️ NBA analyzer failed (skipping): {e}\n")

    # ── STEP 4: SEND EMAIL ────────────────────────────────────────
    print(f"📧 STEP 4 — Sending picks email...")
    try:
        from emailer import send_picks_email

        picks_file = f"logs/{scrape_date}_picks.json"
        if os.path.exists(picks_file):
            with open(picks_file, 'r') as f:
                picks_data = json.load(f)
            send_picks_email(picks_data, scrape_date, graded_summary, cumulative, nba_picks)
            print(f"✅ Step 4 complete\n")
        else:
            print(f"❌ No picks file found to email\n")
    except Exception as e:
        print(f"❌ Emailer failed: {e}")
        import traceback; traceback.print_exc()

    # ── DONE ──────────────────────────────────────────────────────
    end_time = datetime.now()
    duration = (end_time - start_time).seconds
    minutes = duration // 60
    seconds = duration % 60

    print(f"\n{'='*60}")
    print(f"✅ ALL DONE — {scrape_date}")
    print(f"⏱️  Total time: {minutes}m {seconds}s")
    print(f"📧 Check your inbox for today's picks!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(run_all())