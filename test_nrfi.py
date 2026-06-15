# test_nrfi.py
import asyncio
from datetime import datetime
from scraper import run_nrfi_scraper

async def main():
    scrape_date = datetime.now().strftime("%Y-%m-%d")
    result = await run_nrfi_scraper(scrape_date)
    print("\n=== RESULT ===")
    print(f"Team records: {len(result.get('team_records', []))} rows")
    print(f"Batting records: {len(result.get('batting_records', []))} rows")
    print(f"Pitcher records: {len(result.get('pitcher_records', []))} rows")
    print(f"Matchups: {len(result.get('matchups', []))} cards")
    print(f"NRFI scores: {result.get('nrfi_scores', [])}")
    
    # Show first matchup if available
    matchups = result.get('matchups', [])
    if matchups:
        first = matchups[0]
        if isinstance(first, list):
            print(f"\nFirst matchup card ({len(first)} rows):")
            for row in first[:5]:
                print(f"  {row}")
        elif isinstance(first, dict):
            raw = first.get('raw_text', '')
            print(f"\nRaw text preview ({len(raw)} chars):")
            print(raw[:500])

asyncio.run(main())