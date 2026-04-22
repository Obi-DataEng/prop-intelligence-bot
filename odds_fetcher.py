import requests
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
BASE_URL = "https://api.the-odds-api.com/v4"

PROP_MARKETS = [
    "batter_home_runs",
    "batter_hits",
    "batter_total_bases",
    "pitcher_strikeouts",
    "batter_strikeouts",
]

GAME_MARKETS = "h2h,spreads,totals"

BOOKMAKERS = "fanduel,betmgm,williamhill_us,us2espnbet"

BOOK_LABELS = {
    "fanduel": "FD",
    "betmgm": "MGM",
    "williamhill_us": "CZS",
    "us2espnbet": "SCR"
}

def get_mlb_game_odds():
    """Get all MLB game odds — ML, spread, O/U from all 4 books"""
    url = f"{BASE_URL}/sports/baseball_mlb/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "us,us2",
        "markets": GAME_MARKETS,
        "bookmakers": BOOKMAKERS,
        "oddsFormat": "american"
    }
    response = requests.get(url, params=params)
    remaining = response.headers.get('x-requests-remaining')
    print(f"   📊 Requests remaining: {remaining}")

    if response.status_code != 200:
        print(f"   ❌ Game odds error: {response.status_code} — {response.text}")
        return []

    games = response.json()
    structured = []

    for game in games:
        game_data = {
            "id": game['id'],
            "home_team": game['home_team'],
            "away_team": game['away_team'],
            "commence_time": game['commence_time'],
            "odds_by_book": {}
        }

        for bookmaker in game.get('bookmakers', []):
            book_key = bookmaker['key']
            book_label = BOOK_LABELS.get(book_key, book_key)
            book_odds = {
                "ml_home": None, "ml_away": None,
                "spread_home": None, "spread_home_odds": None,
                "spread_away": None, "spread_away_odds": None,
                "total_line": None, "over_odds": None, "under_odds": None
            }

            for market in bookmaker['markets']:
                if market['key'] == 'h2h':
                    for outcome in market['outcomes']:
                        if outcome['name'] == game['home_team']:
                            book_odds['ml_home'] = outcome['price']
                        else:
                            book_odds['ml_away'] = outcome['price']
                elif market['key'] == 'spreads':
                    for outcome in market['outcomes']:
                        if outcome['name'] == game['home_team']:
                            book_odds['spread_home'] = outcome.get('point')
                            book_odds['spread_home_odds'] = outcome['price']
                        else:
                            book_odds['spread_away'] = outcome.get('point')
                            book_odds['spread_away_odds'] = outcome['price']
                elif market['key'] == 'totals':
                    for outcome in market['outcomes']:
                        if outcome['name'] == 'Over':
                            book_odds['total_line'] = outcome.get('point')
                            book_odds['over_odds'] = outcome['price']
                        else:
                            book_odds['under_odds'] = outcome['price']

            game_data['odds_by_book'][book_label] = book_odds

        structured.append(game_data)

        # Print side-by-side comparison
        away = game_data['away_team']
        home = game_data['home_team']
        print(f"\n   ⚾ {away} @ {home}")
        for book, odds in game_data['odds_by_book'].items():
            print(f"      {book:>3}: ML {str(odds['ml_away']):>5}/{str(odds['ml_home']):>5} | "
                  f"RL {str(odds['spread_away']):>5} ({str(odds['spread_away_odds']):>5}) | "
                  f"O/U {odds['total_line']} "
                  f"O:{str(odds['over_odds']):>5} U:{str(odds['under_odds']):>5}")

    return structured

def get_mlb_player_props(games):
    """Get player props for all games from all 4 books"""
    all_props = {}

    for game in games:
        game_id = game['id']
        away = game['away_team']
        home = game['home_team']
        matchup = f"{away}@{home}"

        url = f"{BASE_URL}/sports/baseball_mlb/events/{game_id}/odds"
        params = {
            "apiKey": API_KEY,
            "regions": "us,us2",
            "markets": ",".join(PROP_MARKETS),
            "bookmakers": BOOKMAKERS,
            "oddsFormat": "american"
        }

        response = requests.get(url, params=params)
        remaining = response.headers.get('x-requests-remaining')

        if response.status_code != 200:
            print(f"   ⚠️ No props for {matchup}: {response.status_code}")
            continue

        data = response.json()
        game_props = {
            "hr": [],
            "hits": [],
            "total_bases": [],
            "pitcher_k": [],
            "batter_k": [],
        }

        for bookmaker in data.get('bookmakers', []):
            book_key = bookmaker['key']
            book_label = BOOK_LABELS.get(book_key, book_key)

            for market in bookmaker['markets']:
                for outcome in market['outcomes']:
                    prop = {
                        "player": outcome['name'],
                        "line": outcome.get('point'),
                        "odds": outcome['price'],
                        "pick": outcome.get('description', 'Over'),
                        "book": book_label
                    }
                    if market['key'] == 'batter_home_runs':
                        game_props['hr'].append(prop)
                    elif market['key'] == 'batter_hits':
                        game_props['hits'].append(prop)
                    elif market['key'] == 'batter_total_bases':
                        game_props['total_bases'].append(prop)
                    elif market['key'] == 'pitcher_strikeouts':
                        game_props['pitcher_k'].append(prop)
                    elif market['key'] == 'batter_strikeouts':
                        game_props['batter_k'].append(prop)

        total_props = sum(len(v) for v in game_props.values())
        print(f"   ✅ {matchup}: {total_props} props | "
              f"HR:{len(game_props['hr'])} "
              f"Hits:{len(game_props['hits'])} "
              f"TB:{len(game_props['total_bases'])} "
              f"PitcherK:{len(game_props['pitcher_k'])} "
              f"BatterK:{len(game_props['batter_k'])} "
              f"| Remaining: {remaining}")

        # Show sample props with book comparison
        if game_props['hr']:
            print(f"      HR sample:")
            seen = set()
            for prop in game_props['hr'][:8]:
                key = f"{prop['player']}-{prop['pick']}"
                if key not in seen:
                    seen.add(key)
                    books_for_player = [
                        f"{p['book']}:{p['odds']}"
                        for p in game_props['hr']
                        if p['player'] == prop['player']
                        and p['pick'] == prop['pick']
                    ]
                    print(f"        {prop['player']} ({prop['pick']}) | {' | '.join(books_for_player)}")

        all_props[matchup] = game_props

    return all_props

def fetch_all_odds():
    """Main function — fetch all game odds and player props"""
    scrape_date = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*50}")
    print(f"💰 Fetching Multi-Book Odds — {scrape_date}")
    print(f"📚 Books: FanDuel | BetMGM | Caesars | theScore")
    print(f"{'='*50}\n")

    print("⚾ Fetching MLB game odds...")
    games = get_mlb_game_odds()
    print(f"\n✅ {len(games)} games found")

    print(f"\n🎯 Fetching player props for all games...")
    props = get_mlb_player_props(games)
    print(f"\n✅ Props fetched for {len(props)} games")

    output = {
        "date": scrape_date,
        "books": ["FD", "MGM", "CZS", "SCR"],
        "games": games,
        "player_props": props
    }

    filepath = f"logs/{scrape_date}_odds.json"
    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\n💾 Odds saved to {filepath}")

    return output

def fetch_nba_odds():
    """Fetch NBA game odds and player props from The Odds API"""
    print(f"\n{'='*50}")
    print(f"🏀 Fetching NBA Odds — {datetime.now().strftime('%Y-%m-%d')}")
    print(f"📚 Books: FanDuel | BetMGM | Caesars | theScore")
    print(f"{'='*50}\n")

    headers = {"apiKey": API_KEY}
    all_odds = {"games": [], "player_props": {}}

    # ── STEP 1: Game odds ──────────────────────────────
    print("🏀 Fetching NBA game odds...")
    url = f"{BASE_URL}/sports/basketball_nba/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "us,us2",
        "markets": "h2h,spreads,totals",
        "bookmakers": "fanduel,betmgm,williamhill_us,us2espnbet",
        "oddsFormat": "american"
    }

    response = requests.get(url, params=params)
    remaining = response.headers.get('x-requests-remaining', 'N/A')
    print(f"   📊 Requests remaining: {remaining}")

    if response.status_code != 200:
        print(f"   ❌ Game odds error: {response.status_code}")
        return all_odds

    games = response.json()
    if not games:
        print("   ⚠️ No NBA games found today")
        return all_odds

    print(f"   ✅ {len(games)} games found\n")

    for game in games:
        home = game['home_team']
        away = game['away_team']
        game_id = game['id']
        commence = game.get('commence_time', '')

        game_odds = {
            "game_id": game_id,
            "home_team": home,
            "away_team": away,
            "commence_time": commence,
            "bookmakers": {}
        }

        for bm in game.get('bookmakers', []):
            book = bm['key']
            book_label = {
                'fanduel': 'FD',
                'betmgm': 'MGM',
                'williamhill_us': 'CZS',
                'us2espnbet': 'ESPN'
            }.get(book, book)

            book_data = {}
            for market in bm.get('markets', []):
                key = market['key']
                if key == 'h2h':
                    for outcome in market['outcomes']:
                        if outcome['name'] == home:
                            book_data['home_ml'] = outcome['price']
                        else:
                            book_data['away_ml'] = outcome['price']
                elif key == 'spreads':
                    for outcome in market['outcomes']:
                        if outcome['name'] == home:
                            book_data['home_spread'] = outcome['point']
                            book_data['home_spread_odds'] = outcome['price']
                        else:
                            book_data['away_spread'] = outcome['point']
                            book_data['away_spread_odds'] = outcome['price']
                elif key == 'totals':
                    for outcome in market['outcomes']:
                        if outcome['name'] == 'Over':
                            book_data['total'] = outcome['point']
                            book_data['over_odds'] = outcome['price']
                        else:
                            book_data['under_odds'] = outcome['price']

            game_odds['bookmakers'][book_label] = book_data

        # Print game summary
        fd = game_odds['bookmakers'].get('FD', {})
        czs = game_odds['bookmakers'].get('CZS', {})
        mgm = game_odds['bookmakers'].get('MGM', {})

        print(f"   🏀 {away} @ {home}")
        if fd:
            print(f"       FD: ML {fd.get('away_ml','N/A')}/{fd.get('home_ml','N/A')} | "
                  f"Spread {fd.get('away_spread','N/A')} | "
                  f"O/U {fd.get('total','N/A')}")
        if czs:
            print(f"      CZS: ML {czs.get('away_ml','N/A')}/{czs.get('home_ml','N/A')} | "
                  f"Spread {czs.get('away_spread','N/A')} | "
                  f"O/U {czs.get('total','N/A')}")
        if mgm:
            print(f"      MGM: ML {mgm.get('away_ml','N/A')}/{mgm.get('home_ml','N/A')} | "
                  f"Spread {mgm.get('away_spread','N/A')} | "
                  f"O/U {mgm.get('total','N/A')}")
        print()

        all_odds['games'].append(game_odds)

    # ── STEP 2: Player props ───────────────────────────
    print("🎯 Fetching NBA player props...")

    nba_prop_markets = [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_threes",
        "player_points_rebounds_assists",
        "player_points_rebounds",
        "player_points_assists",
        "player_steals",
        "player_blocks"
    ]

    for game in all_odds['games']:
        game_id = game['game_id']
        home = game['home_team']
        away = game['away_team']
        game_key = f"{away}@{home}"

        url = f"{BASE_URL}/sports/basketball_nba/events/{game_id}/odds"
        params = {
            "apiKey": API_KEY,
            "regions": "us,us2",
            "markets": ",".join(nba_prop_markets),
            "bookmakers": "fanduel,betmgm,williamhill_us,us2espnbet",
            "oddsFormat": "american"
        }

        response = requests.get(url, params=params)
        remaining = response.headers.get('x-requests-remaining', 'N/A')

        if response.status_code != 200:
            print(f"   ❌ Props error for {game_key}: {response.status_code}")
            continue

        event_data = response.json()
        game_props = {}

        for bm in event_data.get('bookmakers', []):
            book = bm['key']
            book_label = {
                'fanduel': 'FD',
                'betmgm': 'MGM',
                'williamhill_us': 'CZS',
                'us2espnbet': 'ESPN'
            }.get(book, book)

            for market in bm.get('markets', []):
                market_key = market['key']
                if market_key not in game_props:
                    game_props[market_key] = {}

                for outcome in market.get('outcomes', []):
                    player = outcome.get('description', outcome.get('name', ''))
                    name = outcome['name']  # Over/Under
                    price = outcome['price']
                    point = outcome.get('point')

                    if player not in game_props[market_key]:
                        game_props[market_key][player] = {'line': point}

                    if name == 'Over':
                        if book_label not in game_props[market_key][player]:
                            game_props[market_key][player][book_label] = {}
                        game_props[market_key][player][book_label]['over'] = price
                        game_props[market_key][player]['line'] = point
                    elif name == 'Under':
                        if book_label not in game_props[market_key][player]:
                            game_props[market_key][player][book_label] = {}
                        game_props[market_key][player][book_label]['under'] = price

        all_odds['player_props'][game_key] = game_props

        # Count props
        total_props = sum(len(v) for v in game_props.values())
        print(f"   ✅ {away}@{home}: {total_props} props | Remaining: {remaining}")

    # Save odds
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_file = f"logs/{date_str}_nba_odds.json"
    with open(output_file, 'w') as f:
        json.dump(all_odds, f, indent=2)
    print(f"\n💾 NBA odds saved to {output_file}")
    print(f"✅ {len(all_odds['games'])} games, props fetched")

    return all_odds

if __name__ == "__main__":
    fetch_all_odds()