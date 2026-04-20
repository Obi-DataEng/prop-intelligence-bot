import asyncio
import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def run_all():
    scrape_date = datetime.now().strftime("%Y-%m-%d")
    start_time = datetime.now()

    print(f"\n{'='*60}")
    print(f"🤖 MLB PICKS BOT — {scrape_date}")
    print(f"⏰ Started at {start_time.strftime('%I:%M %p')}")
    print(f"{'='*60}\n")

    # ── STEP 1: SCRAPE PROPFINDER ──────────────────────
    print(f"📡 STEP 1/4 — Scraping PropFinder...")
    try:
        from scraper import run_scraper
        await run_scraper()
        print(f"✅ Step 1 complete\n")
    except Exception as e:
        print(f"❌ Scraper failed: {e}")
        print(f"⚠️  Continuing without PropFinder data...\n")

    # ── STEP 2: FETCH ODDS ─────────────────────────────
    print(f"💰 STEP 2/4 — Fetching odds from 4 books...")
    try:
        from odds_fetcher import fetch_all_odds
        fetch_all_odds()
        print(f"✅ Step 2 complete\n")
    except Exception as e:
        print(f"❌ Odds fetcher failed: {e}")
        print(f"⚠️  Continuing without fresh odds...\n")

    # ── STEP 3: ANALYZE & GENERATE PICKS ──────────────
    print(f"🧠 STEP 3/4 — Generating picks with Claude...")
    picks = None
    try:
        from parser import run_parser
        from analyzer import load_odds, analyze_and_generate_picks

        raw_data = {}
        tabs = ['hr_matchups', 'exit_velo', 'pitcher_summary',
                'park_factors', 'weather', 'projections']
        for tab in tabs:
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
            print(f"✅ Step 3 complete — picks saved\n")
        else:
            print(f"❌ No picks generated\n")

    except Exception as e:
        print(f"❌ Analyzer failed: {e}")
        import traceback
        traceback.print_exc()

    # ── STEP 4: SEND EMAIL ─────────────────────────────
    print(f"📧 STEP 4/4 — Sending picks email...")
    try:
        from emailer import send_picks_email
        if picks:
            send_picks_email(picks, scrape_date)
            print(f"✅ Step 4 complete\n")
        else:
            picks_file = f"logs/{scrape_date}_picks.json"
            if os.path.exists(picks_file):
                with open(picks_file, 'r') as f:
                    picks_data = json.load(f)
                send_picks_email(picks_data, scrape_date)
                print(f"✅ Step 4 complete\n")
            else:
                print(f"❌ No picks to email\n")
    except Exception as e:
        print(f"❌ Emailer failed: {e}")
        import traceback
        traceback.print_exc()

    # ── DONE ───────────────────────────────────────────
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