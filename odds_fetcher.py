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

if __name__ == "__main__":
    fetch_all_odds()