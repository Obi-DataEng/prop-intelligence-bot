import requests
import os
import json
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
BASE_URL = "https://api.the-odds-api.com/v4"

GAME_MARKETS = "h2h,spreads,totals"
BOOKMAKERS = "fanduel,betmgm,williamhill_us,us2espnbet"

BOOK_LABELS = {
    "fanduel": "FD",
    "betmgm": "MGM",
    "williamhill_us": "CZS",
    "us2espnbet": "ESPN",
}

MLB_PROP_MARKETS = [
    "batter_home_runs",
    "batter_hits",
    "batter_total_bases",
    "pitcher_strikeouts",
    "batter_strikeouts",
]

BASKETBALL_PROP_MARKETS = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_points_rebounds_assists",
    "player_points_rebounds",
    "player_points_assists",
    "player_rebounds_assists",
    "player_steals",
    "player_blocks",
]


def ensure_api_key():
    if not API_KEY:
        raise RuntimeError("Missing ODDS_API_KEY in .env")


def request_json(url, params, label):
    response = requests.get(url, params=params, timeout=45)

    remaining = response.headers.get("x-requests-remaining", "N/A")
    used = response.headers.get("x-requests-used", "N/A")
    print(f"   📊 Requests remaining: {remaining} | Used: {used}")

    if response.status_code != 200:
        print(
            f"   ❌ {label} error: "
            f"{response.status_code} — {response.text[:500]}"
        )
        return None

    return response.json()


# ============================================================
# MLB
# ============================================================

def get_mlb_game_odds():
    """Get MLB ML, spread/run line, and total odds."""
    ensure_api_key()

    url = f"{BASE_URL}/sports/baseball_mlb/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "us,us2",
        "markets": GAME_MARKETS,
        "bookmakers": BOOKMAKERS,
        "oddsFormat": "american",
    }

    games = request_json(url, params, "MLB game odds")
    if games is None:
        return []

    structured = []

    for game in games:
        game_data = {
            "id": game["id"],
            "home_team": game["home_team"],
            "away_team": game["away_team"],
            "commence_time": game.get("commence_time", ""),
            "odds_by_book": {},
        }

        for bookmaker in game.get("bookmakers", []):
            book_key = bookmaker["key"]
            book_label = BOOK_LABELS.get(book_key, book_key)

            book_odds = {
                "ml_home": None,
                "ml_away": None,
                "spread_home": None,
                "spread_home_odds": None,
                "spread_away": None,
                "spread_away_odds": None,
                "total_line": None,
                "over_odds": None,
                "under_odds": None,
            }

            for market in bookmaker.get("markets", []):
                if market["key"] == "h2h":
                    for outcome in market.get("outcomes", []):
                        if outcome["name"] == game["home_team"]:
                            book_odds["ml_home"] = outcome["price"]
                        elif outcome["name"] == game["away_team"]:
                            book_odds["ml_away"] = outcome["price"]

                elif market["key"] == "spreads":
                    for outcome in market.get("outcomes", []):
                        if outcome["name"] == game["home_team"]:
                            book_odds["spread_home"] = outcome.get("point")
                            book_odds["spread_home_odds"] = outcome["price"]
                        elif outcome["name"] == game["away_team"]:
                            book_odds["spread_away"] = outcome.get("point")
                            book_odds["spread_away_odds"] = outcome["price"]

                elif market["key"] == "totals":
                    for outcome in market.get("outcomes", []):
                        if outcome["name"] == "Over":
                            book_odds["total_line"] = outcome.get("point")
                            book_odds["over_odds"] = outcome["price"]
                        elif outcome["name"] == "Under":
                            book_odds["under_odds"] = outcome["price"]

            game_data["odds_by_book"][book_label] = book_odds

        structured.append(game_data)

        away = game_data["away_team"]
        home = game_data["home_team"]
        print(f"\n   ⚾ {away} @ {home}")

        for book, odds in game_data["odds_by_book"].items():
            print(
                f"      {book:>4}: "
                f"ML {str(odds['ml_away']):>5}/"
                f"{str(odds['ml_home']):>5} | "
                f"RL {str(odds['spread_away']):>5} "
                f"({str(odds['spread_away_odds']):>5}) | "
                f"O/U {odds['total_line']} "
                f"O:{str(odds['over_odds']):>5} "
                f"U:{str(odds['under_odds']):>5}"
            )

    return structured


def get_mlb_player_props(games):
    """Get MLB player props for all games."""
    ensure_api_key()
    all_props = {}

    for game in games:
        game_id = game["id"]
        away = game["away_team"]
        home = game["home_team"]
        matchup = f"{away}@{home}"

        url = f"{BASE_URL}/sports/baseball_mlb/events/{game_id}/odds"
        params = {
            "apiKey": API_KEY,
            "regions": "us,us2",
            "markets": ",".join(MLB_PROP_MARKETS),
            "bookmakers": BOOKMAKERS,
            "oddsFormat": "american",
        }

        data = request_json(url, params, f"MLB props for {matchup}")

        if data is None:
            continue

        game_props = {
            "hr": [],
            "hits": [],
            "total_bases": [],
            "pitcher_k": [],
            "batter_k": [],
        }

        for bookmaker in data.get("bookmakers", []):
            book_key = bookmaker["key"]
            book_label = BOOK_LABELS.get(book_key, book_key)

            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    prop = {
                        "player": outcome["name"],
                        "line": outcome.get("point"),
                        "odds": outcome["price"],
                        "pick": outcome.get("description", "Over"),
                        "book": book_label,
                    }

                    if market["key"] == "batter_home_runs":
                        game_props["hr"].append(prop)
                    elif market["key"] == "batter_hits":
                        game_props["hits"].append(prop)
                    elif market["key"] == "batter_total_bases":
                        game_props["total_bases"].append(prop)
                    elif market["key"] == "pitcher_strikeouts":
                        game_props["pitcher_k"].append(prop)
                    elif market["key"] == "batter_strikeouts":
                        game_props["batter_k"].append(prop)

        total_props = sum(len(v) for v in game_props.values())
        print(f"   ✅ {matchup}: {total_props} MLB prop outcomes")

        all_props[matchup] = game_props

    return all_props


def fetch_all_odds():
    """Existing MLB odds workflow."""
    scrape_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'=' * 50}")
    print(f"💰 Fetching MLB Multi-Book Odds — {scrape_date}")
    print("📚 Books: FanDuel | BetMGM | Caesars | ESPN BET")
    print(f"{'=' * 50}\n")

    print("⚾ Fetching MLB game odds...")
    games = get_mlb_game_odds()
    print(f"\n✅ {len(games)} MLB games found")

    print("\n🎯 Fetching MLB player props...")
    props = get_mlb_player_props(games)
    print(f"\n✅ MLB props fetched for {len(props)} games")

    output = {
        "date": scrape_date,
        "books": ["FD", "MGM", "CZS", "ESPN"],
        "games": games,
        "player_props": props,
    }

    filepath = f"logs/{scrape_date}_odds.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n💾 MLB odds saved to {filepath}")
    return output


# ============================================================
# GENERIC NBA / WNBA
# ============================================================

def parse_basketball_game(game):
    home = game["home_team"]
    away = game["away_team"]

    game_odds = {
        "game_id": game["id"],
        "home_team": home,
        "away_team": away,
        "commence_time": game.get("commence_time", ""),
        "bookmakers": {},
    }

    for bm in game.get("bookmakers", []):
        book_label = BOOK_LABELS.get(bm["key"], bm["key"])

        book_data = {
            "home_ml": None,
            "away_ml": None,
            "home_spread": None,
            "home_spread_odds": None,
            "away_spread": None,
            "away_spread_odds": None,
            "total": None,
            "over_odds": None,
            "under_odds": None,
        }

        for market in bm.get("markets", []):
            key = market["key"]

            if key == "h2h":
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == home:
                        book_data["home_ml"] = outcome["price"]
                    elif outcome["name"] == away:
                        book_data["away_ml"] = outcome["price"]

            elif key == "spreads":
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == home:
                        book_data["home_spread"] = outcome.get("point")
                        book_data["home_spread_odds"] = outcome["price"]
                    elif outcome["name"] == away:
                        book_data["away_spread"] = outcome.get("point")
                        book_data["away_spread_odds"] = outcome["price"]

            elif key == "totals":
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == "Over":
                        book_data["total"] = outcome.get("point")
                        book_data["over_odds"] = outcome["price"]
                    elif outcome["name"] == "Under":
                        book_data["under_odds"] = outcome["price"]

        game_odds["bookmakers"][book_label] = book_data

    return game_odds


def print_basketball_game(game_odds, emoji="🏀"):
    away = game_odds["away_team"]
    home = game_odds["home_team"]

    print(f"   {emoji} {away} @ {home}")

    for book, odds in game_odds["bookmakers"].items():
        print(
            f"      {book:>4}: "
            f"ML {str(odds.get('away_ml')):>5}/"
            f"{str(odds.get('home_ml')):>5} | "
            f"Spread "
            f"{str(odds.get('away_spread')):>5} "
            f"({str(odds.get('away_spread_odds')):>5}) | "
            f"O/U {str(odds.get('total')):>5} "
            f"O:{str(odds.get('over_odds')):>5} "
            f"U:{str(odds.get('under_odds')):>5}"
        )

    print()


def fetch_basketball_game_odds(sport_key, league_name):
    ensure_api_key()

    url = f"{BASE_URL}/sports/{sport_key}/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "us,us2",
        "markets": GAME_MARKETS,
        "bookmakers": BOOKMAKERS,
        "oddsFormat": "american",
    }

    data = request_json(
        url,
        params,
        f"{league_name} game odds",
    )

    if data is None:
        return []

    games = [parse_basketball_game(game) for game in data]

    for game in games:
        print_basketball_game(game)

    return games


def fetch_basketball_player_props(
    games,
    sport_key,
    league_name,
):
    ensure_api_key()
    all_props = {}

    for game in games:
        game_id = game["game_id"]
        home = game["home_team"]
        away = game["away_team"]
        game_key = f"{away}@{home}"

        url = (
            f"{BASE_URL}/sports/{sport_key}/events/"
            f"{game_id}/odds"
        )

        params = {
            "apiKey": API_KEY,
            "regions": "us,us2",
            "markets": ",".join(BASKETBALL_PROP_MARKETS),
            "bookmakers": BOOKMAKERS,
            "oddsFormat": "american",
        }

        event_data = request_json(
            url,
            params,
            f"{league_name} props for {game_key}",
        )

        if event_data is None:
            continue

        game_props = {}

        for bm in event_data.get("bookmakers", []):
            book_label = BOOK_LABELS.get(
                bm["key"],
                bm["key"],
            )

            for market in bm.get("markets", []):
                market_key = market["key"]
                game_props.setdefault(market_key, {})

                for outcome in market.get("outcomes", []):
                    # The Odds API uses description for player name
                    # on Over/Under player prop markets.
                    player = outcome.get(
                        "description",
                        outcome.get("name", ""),
                    )

                    side = outcome.get("name", "")
                    price = outcome.get("price")
                    point = outcome.get("point")

                    game_props[market_key].setdefault(
                        player,
                        {"line": point},
                    )

                    game_props[market_key][player][
                        "line"
                    ] = point

                    game_props[market_key][player].setdefault(
                        book_label,
                        {},
                    )

                    # Preserve each sportsbook's own line. The legacy
                    # top-level "line" remains for backward compatibility.
                    game_props[market_key][player][
                        book_label
                    ]["line"] = point

                    if side == "Over":
                        game_props[market_key][player][
                            book_label
                        ]["over"] = price

                    elif side == "Under":
                        game_props[market_key][player][
                            book_label
                        ]["under"] = price

        all_props[game_key] = game_props

        total_players = sum(
            len(players)
            for players in game_props.values()
        )

        print(
            f"   ✅ {game_key}: "
            f"{total_players} player/market combinations"
        )

    return all_props


def fetch_basketball_odds(
    sport_key,
    league_name,
    output_suffix,
):
    scrape_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'=' * 50}")
    print(
        f"🏀 Fetching {league_name} Odds — "
        f"{scrape_date}"
    )
    print(
        "📚 Books: FanDuel | BetMGM | "
        "Caesars | ESPN BET"
    )
    print(
        "🎲 Markets: Moneyline | Spread | "
        "Game O/U | Player Props"
    )
    print(f"{'=' * 50}\n")

    print(
        f"🏀 Fetching {league_name} "
        f"game odds..."
    )

    games = fetch_basketball_game_odds(
        sport_key,
        league_name,
    )

    print(
        f"\n✅ {len(games)} "
        f"{league_name} games found"
    )

    print(
        f"\n🎯 Fetching {league_name} "
        f"player props..."
    )

    props = fetch_basketball_player_props(
        games,
        sport_key,
        league_name,
    )

    print(
        f"\n✅ {league_name} props fetched "
        f"for {len(props)} games"
    )

    output = {
        "date": scrape_date,
        "league": league_name,
        "sport_key": sport_key,
        "books": [
            "FD",
            "MGM",
            "CZS",
            "ESPN",
        ],
        "game_markets": [
            "moneyline",
            "spread",
            "total",
        ],
        "player_prop_markets": BASKETBALL_PROP_MARKETS,
        "games": games,
        "player_props": props,
    }

    output_file = (
        f"logs/{scrape_date}_{output_suffix}_odds.json"
    )

    with open(
        output_file,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"\n💾 {league_name} odds saved to "
        f"{output_file}"
    )

    print(
        f"✅ {len(games)} games | "
        f"props for {len(props)} games"
    )

    return output


def fetch_nba_odds():
    return fetch_basketball_odds(
        sport_key="basketball_nba",
        league_name="NBA",
        output_suffix="nba",
    )


def fetch_wnba_odds():
    return fetch_basketball_odds(
        sport_key="basketball_wnba",
        league_name="WNBA",
        output_suffix="wnba",
    )


# ============================================================
# CFB / NCAAF — GAME MARKETS ONLY
# ============================================================

CFB_BOOKMAKERS = "fanduel,williamhill_us"


def parse_cfb_game(game):
    """
    Convert The Odds API NCAAF game response into our
    standard game-market structure.

    CFB V1 intentionally supports GAME MARKETS ONLY:
      - Moneyline
      - Spread
      - Game Total

    No college player props are fetched.
    """
    home = game["home_team"]
    away = game["away_team"]

    game_odds = {
        "game_id": game["id"],
        "home_team": home,
        "away_team": away,
        "commence_time": game.get("commence_time", ""),
        "bookmakers": {},
    }

    for bm in game.get("bookmakers", []):
        book_key = bm["key"]
        book_label = BOOK_LABELS.get(
            book_key,
            book_key,
        )

        book_data = {
            "home_ml": None,
            "away_ml": None,
            "home_spread": None,
            "home_spread_odds": None,
            "away_spread": None,
            "away_spread_odds": None,
            "total": None,
            "over_odds": None,
            "under_odds": None,
        }

        for market in bm.get("markets", []):
            key = market["key"]

            # MONEYLINE
            if key == "h2h":
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == home:
                        book_data["home_ml"] = outcome["price"]

                    elif outcome["name"] == away:
                        book_data["away_ml"] = outcome["price"]

            # SPREAD
            elif key == "spreads":
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == home:
                        book_data["home_spread"] = outcome.get("point")
                        book_data["home_spread_odds"] = outcome["price"]

                    elif outcome["name"] == away:
                        book_data["away_spread"] = outcome.get("point")
                        book_data["away_spread_odds"] = outcome["price"]

            # GAME TOTAL
            elif key == "totals":
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == "Over":
                        book_data["total"] = outcome.get("point")
                        book_data["over_odds"] = outcome["price"]

                    elif outcome["name"] == "Under":
                        book_data["under_odds"] = outcome["price"]

        game_odds["bookmakers"][book_label] = book_data

    return game_odds


def print_cfb_game(game):
    """Pretty-print one CFB matchup."""
    away = game["away_team"]
    home = game["home_team"]

    print(f"\n   🏈 {away} @ {home}")

    for book, odds in game["bookmakers"].items():
        print(
            f"      {book:>4}: "
            f"ML {str(odds.get('away_ml')):>6}/"
            f"{str(odds.get('home_ml')):>6} | "
            f"Spread "
            f"{str(odds.get('away_spread')):>6} "
            f"({str(odds.get('away_spread_odds')):>6}) | "
            f"O/U {str(odds.get('total')):>6} "
            f"O:{str(odds.get('over_odds')):>6} "
            f"U:{str(odds.get('under_odds')):>6}"
        )


def fetch_cfb_odds():
    """
    Fetch NCAAF/CFB game odds from FanDuel and Caesars only.

    Supported markets:
      - Moneyline
      - Spread
      - Game total

    College player props are deliberately excluded.
    """
    ensure_api_key()

    scrape_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'=' * 55}")
    print(f"🏈 Fetching CFB Odds — {scrape_date}")
    print("📚 Books: FanDuel | Caesars")
    print("🎲 Markets: Moneyline | Spread | Game Total")
    print("🚫 College player props: DISABLED")
    print(f"{'=' * 55}\n")

    url = (
        f"{BASE_URL}/sports/"
        f"americanfootball_ncaaf/odds"
    )

    params = {
        "apiKey": API_KEY,
        "regions": "us,us2",
        "markets": GAME_MARKETS,
        "bookmakers": CFB_BOOKMAKERS,
        "oddsFormat": "american",
    }

    data = request_json(
        url,
        params,
        "CFB game odds",
    )

    if data is None:
        return {
            "date": scrape_date,
            "league": "CFB",
            "sport_key": "americanfootball_ncaaf",
            "books": ["FD", "CZS"],
            "game_markets": [
                "moneyline",
                "spread",
                "total",
            ],
            "games": [],
        }

    games = [
        parse_cfb_game(game)
        for game in data
    ]

    print(
        f"✅ {len(games)} CFB games found"
    )

    for game in games:
        print_cfb_game(game)

    output = {
        "date": scrape_date,
        "league": "CFB",
        "sport_key": "americanfootball_ncaaf",
        "books": [
            "FD",
            "CZS",
        ],
        "game_markets": [
            "moneyline",
            "spread",
            "total",
        ],
        "player_props_enabled": False,
        "games": games,
    }

    output_file = (
        f"logs/{scrape_date}_cfb_odds.json"
    )

    with open(
        output_file,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"\n💾 CFB odds saved to "
        f"{output_file}"
    )

    return output

# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "mlb"

    if mode == "mlb":
        fetch_all_odds()

    elif mode == "nba":
        fetch_nba_odds()

    elif mode == "wnba":
        fetch_wnba_odds()

    elif mode in ("cfb", "ncaaf"):
        fetch_cfb_odds()

    else:
        print(
            "Usage: python3 odds_fetcher.py "
            "[mlb|nba|wnba|cfb]"
        )
