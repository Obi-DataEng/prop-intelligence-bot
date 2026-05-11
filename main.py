import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from scraper import run_scraper, run_nba_scraper, run_nrfi_scraper
from parser import run_parser
from analyzer import analyze_and_generate_picks, load_odds, generate_nrfi_picks
from odds_fetcher import fetch_mlb_odds, fetch_nba_odds
from grader import run_grader, init_db
from emailer import send_picks_email
from nba_analyzer import analyze_nba_picks
from news_fetcher import fetch_news

def main():
    scrape_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"⚾🏀 MLB + NBA Picks Bot — {scrape_date}")
    print(f"{'='*60}\n")

    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    init_db()

    # ──────────────────────────────────────────────────────────────
    # STEP 0: Fetch news
    # ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"📰 Step 0: Fetching news...")
    print(f"{'='*50}")
    try:
        fetch_news(scrape_date, sport="mlb")
        fetch_news(scrape_date, sport="nba")
        print("   ✅ News fetched")
    except Exception as e:
        print(f"   ⚠️ News fetch error: {e}")

    # ──────────────────────────────────────────────────────────────
    # STEP 1: MLB Scrape
    # ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"⚾ Step 1: MLB Scraping...")
    print(f"{'='*50}")
    try:
        raw_data = asyncio.run(run_scraper())
        print("   ✅ MLB scraping complete")
    except Exception as e:
        print(f"   ❌ MLB scraping failed: {e}")
        raw_data = {}

    # ──────────────────────────────────────────────────────────────
    # STEP 1.5: NRFI Scrape
    # ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"🎰 Step 1.5: NRFI Scraping...")
    print(f"{'='*50}")
    nrfi_data = {}
    try:
        nrfi_data = asyncio.run(run_nrfi_scraper(scrape_date))
        print("   ✅ NRFI scraping complete")
    except Exception as e:
        print(f"   ⚠️ NRFI scraping failed: {e}")

    # ──────────────────────────────────────────────────────────────
    # STEP 2: NBA Scrape
    # ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"🏀 Step 2: NBA Scraping...")
    print(f"{'='*50}")
    try:
        nba_raw_data = asyncio.run(run_nba_scraper())
        print("   ✅ NBA scraping complete")
    except Exception as e:
        print(f"   ⚠️ NBA scraping failed: {e}")
        nba_raw_data = {}

    # Load scraped data from disk if memory dict is empty
    if not raw_data:
        raw_data = {}
        for tab in ['hr_matchups', 'exit_velo', 'pitcher_summary', 'park_factors', 'weather', 'projections']:
            filepath = f"logs/{scrape_date}_{tab}.json"
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    raw_data[tab] = json.load(f)

    if not nba_raw_data:
        nba_raw_data = {}
        for tab in ['nba_player_stats', 'nba_def_matchups', 'nba_hit_rate', 'nba_injury_reports', 'nba_lineups', 'nba_team_stats']:
            filepath = f"logs/{scrape_date}_{tab}.json"
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    nba_raw_data[tab] = json.load(f)

    if not nrfi_data:
        nrfi_file = f"logs/{scrape_date}_nrfi.json"
        if os.path.exists(nrfi_file):
            with open(nrfi_file, 'r') as f:
                nrfi_data = json.load(f)

    # ──────────────────────────────────────────────────────────────
    # STEP 3: Fetch Odds
    # ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"💰 Step 3: Fetching odds...")
    print(f"{'='*50}")
    try:
        mlb_odds = fetch_mlb_odds(scrape_date)
        print("   ✅ MLB odds fetched")
    except Exception as e:
        print(f"   ⚠️ MLB odds error: {e}")
        mlb_odds = None

    try:
        nba_odds = fetch_nba_odds(scrape_date)
        print("   ✅ NBA odds fetched")
    except Exception as e:
        print(f"   ⚠️ NBA odds error: {e}")
        nba_odds = None

    # ──────────────────────────────────────────────────────────────
    # STEP 3.2: Parse MLB data
    # ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"🔧 Step 3.2: Parsing MLB data...")
    print(f"{'='*50}")
    try:
        from parser import run_parser
        parsed_data = run_parser(raw_data, scrape_date)
        print("   ✅ MLB data parsed")
    except Exception as e:
        print(f"   ❌ MLB parse error: {e}")
        parsed_data = {}

    # ──────────────────────────────────────────────────────────────
    # STEP 4: Grade yesterday's picks
    # ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"📊 Step 4: Grading yesterday's picks...")
    print(f"{'='*50}")
    graded_summary = None
    cumulative = None
    try:
        graded_summary, cumulative = run_grader()
        print("   ✅ Grading complete")
    except Exception as e:
        print(f"   ⚠️ Grader error: {e}")
        import traceback; traceback.print_exc()

    # ──────────────────────────────────────────────────────────────
    # STEP 5: Generate MLB picks
    # ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"🤖 Step 5: Generating MLB picks...")
    print(f"{'='*50}")
    picks_data = None
    try:
        picks_data = analyze_and_generate_picks(parsed_data, mlb_odds, scrape_date)
        if picks_data:
            print(f"   ✅ MLB picks generated")
        else:
            print(f"   ⚠️ MLB picks generation returned None")
    except Exception as e:
        print(f"   ❌ MLB analyzer error: {e}")
        import traceback; traceback.print_exc()

    # ──────────────────────────────────────────────────────────────
    # STEP 5.5: Generate NRFI picks
    # ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"🎰 Step 5.5: Generating NRFI picks...")
    print(f"{'='*50}")
    nrfi_picks = []
    if nrfi_data:
        try:
            nrfi_picks = generate_nrfi_picks(nrfi_data, scrape_date)
            print(f"   ✅ {len(nrfi_picks)} NRFI picks generated")
        except Exception as e:
            print(f"   ⚠️ NRFI picks error: {e}")
    else:
        print("   ⚠️ No NRFI data available — skipping")

    # Attach NRFI picks to main picks_data
    if picks_data is None:
        picks_data = {}
    picks_data['nrfi_picks'] = nrfi_picks

    # Save combined MLB + NRFI picks
    if picks_data:
        output_file = f"logs/{scrape_date}_picks.json"
        with open(output_file, 'w') as f:
            json.dump(picks_data, f, indent=2)
        print(f"   💾 MLB + NRFI picks saved to {output_file}")

    # ──────────────────────────────────────────────────────────────
    # STEP 6: Generate NBA picks
    # ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"🏀 Step 6: Generating NBA picks...")
    print(f"{'='*50}")
    nba_picks = None
    try:
        nba_picks = analyze_nba_picks(nba_raw_data, nba_odds, scrape_date)
        if nba_picks:
            nba_output = f"logs/{scrape_date}_nba_picks.json"
            with open(nba_output, 'w') as f:
                json.dump(nba_picks, f, indent=2)
            print(f"   ✅ NBA picks generated and saved")
        else:
            print(f"   ⚠️ NBA picks generation returned None")
    except Exception as e:
        print(f"   ❌ NBA analyzer error: {e}")
        import traceback; traceback.print_exc()

    # ──────────────────────────────────────────────────────────────
    # STEP 7: Send email
    # ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"📧 Step 7: Sending email...")
    print(f"{'='*50}")

    if picks_data:
        try:
            success = send_picks_email(picks_data, scrape_date, graded_summary, cumulative, nba_picks)
            if success:
                print("   ✅ Email sent!")
            else:
                print("   ❌ Email failed")
        except Exception as e:
            print(f"   ❌ Email error: {e}")
            import traceback; traceback.print_exc()
    else:
        print("   ⚠️ No picks data — email skipped")

    print(f"\n{'='*60}")
    print(f"✅ Pipeline complete for {scrape_date}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()