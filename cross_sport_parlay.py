import json
import math
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo


EASTERN = ZoneInfo("America/New_York")
SUPPORTED_LEAGUES = ("WNBA", "CFB", "NFL", "NBA")
MIN_LEG_ODDS = -650
MAX_LEG_ODDS = -180
TARGET_DECIMAL = 6.0       # +500
MIN_DECIMAL = 5.5          # +450
MAX_DECIMAL = 7.0          # +600
MAX_LEGS = 12

PLAYER_MARKET_MAP = {
    "points": "player_points_alternate",
    "rebounds": "player_rebounds_alternate",
    "assists": "player_assists_alternate",
    "three pointers": "player_threes_alternate",
    "threes": "player_threes_alternate",
    "3-pointers made": "player_threes_alternate",
    "pra": "player_points_rebounds_assists_alternate",
    "points + rebounds + assists": "player_points_rebounds_assists_alternate",
    "pr": "player_points_rebounds_alternate",
    "points + rebounds": "player_points_rebounds_alternate",
    "pa": "player_points_assists_alternate",
    "points + assists": "player_points_assists_alternate",
    "ra": "player_rebounds_assists_alternate",
    "rebounds + assists": "player_rebounds_assists_alternate",
    "steals": "player_steals_alternate",
    "blocks": "player_blocks_alternate",
}

MARKET_LABELS = {
    value: key.title() for key, value in PLAYER_MARKET_MAP.items()
}
MARKET_LABELS.update({
    "player_threes_alternate": "3-Pointers Made",
    "player_points_rebounds_assists_alternate": "PRA",
    "player_points_rebounds_alternate": "Points + Rebounds",
    "player_points_assists_alternate": "Points + Assists",
    "player_rebounds_assists_alternate": "Rebounds + Assists",
})


def load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def american_to_decimal(odds):
    odds = float(odds)
    return 1.0 + (100.0 / abs(odds) if odds < 0 else odds / 100.0)


def decimal_to_american(decimal_odds):
    if decimal_odds >= 2:
        return int(round((decimal_odds - 1) * 100))
    return int(round(-100 / (decimal_odds - 1)))


def price_allowed(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return False
    return MIN_LEG_ODDS <= value <= MAX_LEG_ODDS


def normalize(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def game_on_date(game, target_date):
    value = game.get("commence_time")
    if not value:
        return True
    try:
        start = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return start.astimezone(EASTERN).date() == datetime.strptime(
            target_date, "%Y-%m-%d"
        ).date()
    except (TypeError, ValueError):
        return False


def confidence_score(value):
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").lower()
    if "elite" in text or "strong" in text:
        return 90.0
    if "high" in text:
        return 84.0
    if "moderate" in text:
        return 78.0
    if "medium" in text:
        return 74.0
    if "lean" in text:
        return 68.0
    return 62.0


def game_key_from_matchup(matchup):
    parts = re.split(r"\s+@\s+", str(matchup or ""), maxsplit=1)
    return f"{parts[0]}@{parts[1]}" if len(parts) == 2 else ""


def best_player_alt_candidate(league, pick, odds_data):
    player = pick.get("player_name") or pick.get("player")
    matchup = pick.get("game")
    if not player or not matchup:
        return None
    category = str(pick.get("category") or pick.get("market") or "").lower().strip()
    market = PLAYER_MARKET_MAP.get(category)
    if not market:
        for label, key in PLAYER_MARKET_MAP.items():
            if label in category:
                market = key
                break
    if not market:
        return None
    try:
        base_line = float(pick.get("prop_line", pick.get("line")))
    except (TypeError, ValueError):
        return None
    direction = str(pick.get("over_under") or "").lower()
    if direction not in {"over", "under"}:
        return None

    game_key = game_key_from_matchup(matchup)
    players = odds_data.get("player_props", {}).get(game_key, {}).get(market, {})
    prop_data = next(
        (data for name, data in players.items() if normalize(name) == normalize(player)),
        None,
    )
    if not isinstance(prop_data, dict):
        return None

    offers = []
    for book, book_data in prop_data.items():
        if book == "line" or not isinstance(book_data, dict):
            continue
        for offer in book_data.get("offers", []):
            try:
                line, price = float(offer.get("line")), int(offer.get("odds"))
            except (TypeError, ValueError):
                continue
            side = str(offer.get("side") or "").lower()
            safer = line < base_line if direction == "over" else line > base_line
            if side == direction and safer and price_allowed(price):
                offers.append((line, price, book))
    if not offers:
        return None

    # Prefer the safest alternate line, then the best payout at that line.
    safe_line = min(row[0] for row in offers) if direction == "over" else max(row[0] for row in offers)
    exact = [row for row in offers if abs(row[0] - safe_line) < 0.001]
    line, price, book = max(exact, key=lambda row: row[1])
    label = MARKET_LABELS.get(market, category.title())
    return {
        "league": league, "game": matchup,
        "selection": f"{player} {direction.title()} {line:g} {label}",
        "market_type": "player_prop", "player": player,
        "direction": direction.title(), "line": line,
        "book": book, "odds": price,
        "source_pick": pick.get("selection") or f"{player} {direction.title()} {base_line:g}",
        "support_score": confidence_score(
            pick.get("prediction_confidence", pick.get("confidence_score", pick.get("confidence_tier")))
        ),
        "reasoning": (
            f"Safer alternate from the supported {direction.title()} {base_line:g} lean; "
            f"moved to {line:g}."
        ),
        "official_pick": False, "track_result": False,
    }


def best_game_alt_candidate(league, row, odds_data, market_type):
    matchup = row.get("game")
    game_key = game_key_from_matchup(matchup)
    markets = odds_data.get("alternate_game_markets", {}).get(game_key, {})
    try:
        base_line = float(row.get("line"))
    except (TypeError, ValueError):
        return None

    offers = []
    if market_type == "spread":
        team = row.get("team")
        if not team:
            selection = str(row.get("selection") or "")
            team = re.sub(r"\s+[+-]\d+(?:\.\d+)?\s*$", "", selection).strip()
        for offer in markets.get("spreads", []):
            try:
                line, price = float(offer.get("line")), int(offer.get("odds"))
            except (TypeError, ValueError):
                continue
            if normalize(offer.get("team")) == normalize(team) and line > base_line and price_allowed(price):
                offers.append((line, price, offer.get("book"), team, None))
    else:
        direction = str(row.get("over_under") or "").title()
        if direction not in {"Over", "Under"}:
            direction = "Over" if str(row.get("selection", "")).lower().startswith("over") else "Under"
        for offer in markets.get("totals", []):
            try:
                line, price = float(offer.get("line")), int(offer.get("odds"))
            except (TypeError, ValueError):
                continue
            safer = line < base_line if direction == "Over" else line > base_line
            if str(offer.get("side")) == direction and safer and price_allowed(price):
                offers.append((line, price, offer.get("book"), None, direction))
    if not offers:
        return None

    if market_type == "spread":
        safe_line = max(item[0] for item in offers)
    else:
        safe_line = min(item[0] for item in offers) if offers[0][4] == "Over" else max(item[0] for item in offers)
    exact = [item for item in offers if abs(item[0] - safe_line) < 0.001]
    line, price, book, team, direction = max(exact, key=lambda item: item[1])
    selection = f"{team} {line:+g}" if market_type == "spread" else f"{direction} {line:g}"
    return {
        "league": league, "game": matchup, "selection": selection,
        "market_type": market_type, "team": team,
        "direction": direction, "line": line, "book": book, "odds": price,
        "source_pick": row.get("selection"),
        "support_score": confidence_score(row.get("confidence", row.get("prediction_confidence"))),
        "reasoning": f"Safer alternate derived from the supported {row.get('selection')} direction.",
        "official_pick": False, "track_result": False,
    }


def collect_candidates(scrape_date):
    candidates = []
    for league in SUPPORTED_LEAGUES:
        slug = league.lower()
        picks = load_json(f"logs/{scrape_date}_{slug}_picks.json")
        odds = load_json(f"logs/{scrape_date}_{slug}_odds.json")
        if not picks or not odds:
            continue
        daily_keys = {
            f"{game.get('away_team')}@{game.get('home_team')}"
            for game in odds.get("games", []) if game_on_date(game, scrape_date)
        }
        if not daily_keys:
            continue

        if league in {"NBA", "WNBA"}:
            for pick in picks.get("top_picks", []):
                candidate = best_player_alt_candidate(league, pick, odds)
                if candidate and game_key_from_matchup(candidate["game"]) in daily_keys:
                    candidates.append(candidate)

        for row in picks.get("lotto_spread_board", []):
            candidate = best_game_alt_candidate(league, row, odds, "spread")
            if candidate and game_key_from_matchup(candidate["game"]) in daily_keys:
                candidates.append(candidate)
        for row in picks.get("lotto_total_board", []):
            candidate = best_game_alt_candidate(league, row, odds, "total")
            if candidate and game_key_from_matchup(candidate["game"]) in daily_keys:
                candidates.append(candidate)

    unique = {}
    for candidate in candidates:
        key = (candidate["league"], normalize(candidate["game"]), normalize(candidate["selection"]))
        current = unique.get(key)
        if current is None or candidate["odds"] > current["odds"]:
            unique[key] = candidate
    return sorted(unique.values(), key=lambda row: (row["support_score"], row["odds"]), reverse=True)


def choose_parlay(candidates):
    if not candidates:
        return []
    available_sports = {row["league"] for row in candidates}
    pool = candidates[:60]
    states = [([], 1.0, tuple(), frozenset(), 0.0)]

    for candidate in pool:
        additions = []
        game_token = f"{candidate['league']}:{normalize(candidate['game'])}"
        for legs, decimal_odds, games, sports, quality in states:
            if len(legs) >= MAX_LEGS:
                continue
            combined = decimal_odds * american_to_decimal(candidate["odds"])
            if combined > MAX_DECIMAL * 1.12:
                continue
            additions.append((
                legs + [candidate], combined,
                games + (game_token,), sports | {candidate["league"]},
                quality + candidate["support_score"],
            ))
        states.extend(additions)
        # Retain a diverse beam by leg count and approximate combined price.
        buckets = {}
        for state in states:
            key = (len(state[0]), round(state[1], 1), tuple(sorted(state[3])))
            score = state[4] - abs(TARGET_DECIMAL - state[1]) * 4
            if key not in buckets or score > buckets[key][0]:
                buckets[key] = (score, state)
        states = [item[1] for item in sorted(buckets.values(), key=lambda item: item[0], reverse=True)[:3500]]

    valid = []
    require_mix = len(available_sports) >= 2
    for state in states:
        legs, decimal_odds, games, sports, quality = state
        if not (MIN_DECIMAL <= decimal_odds <= MAX_DECIMAL):
            continue
        if require_mix and len(sports) < 2:
            continue
        if len(legs) < 2:
            continue
        average_quality = quality / len(legs)
        valid.append((abs(decimal_odds - TARGET_DECIMAL), -average_quality, len(legs), state))
    if valid:
        return min(valid, key=lambda item: item[:3])[3][0]

    # A board should not disappear merely because very safe, heavily juiced
    # alternates cannot land inside the exact target window. Return the closest
    # verified combination and clearly label below that the target was missed.
    fallback = []
    for state in states:
        legs, decimal_odds, games, sports, quality = state
        if len(legs) < 2:
            continue
        if require_mix and len(sports) < 2:
            continue
        average_quality = quality / len(legs)
        fallback.append((abs(decimal_odds - TARGET_DECIMAL), -average_quality, len(legs), state))
    return min(fallback, key=lambda item: item[:3])[3][0] if fallback else []


def build_cross_sport_parlay(scrape_date=None):
    scrape_date = scrape_date or datetime.now(EASTERN).strftime("%Y-%m-%d")
    candidates = collect_candidates(scrape_date)
    legs = choose_parlay(candidates)
    combined_decimal = math.prod(american_to_decimal(row["odds"]) for row in legs) if legs else None
    combined_american = decimal_to_american(combined_decimal) if combined_decimal else None
    target_reached = bool(combined_decimal and MIN_DECIMAL <= combined_decimal <= MAX_DECIMAL)
    result = {
        "date": scrape_date,
        "name": "+500 Cross-Sport Alt Parlay",
        "sports_allowed": list(SUPPORTED_LEAGUES),
        "mlb_excluded": True,
        "target_odds_range": "+450 to +600",
        "available": bool(legs),
        "target_reached": target_reached,
        "legs": legs,
        "leg_count": len(legs),
        "combined_decimal_odds": round(combined_decimal, 3) if combined_decimal else None,
        "combined_american_odds": combined_american,
        "implied_probability_pct": round(100 / combined_decimal, 1) if combined_decimal else None,
        "candidate_count": len(candidates),
        "official_pick": False,
        "track_result": False,
        "notice": "Entertainment-only alternate-line parlay; excluded from grading and official records.",
    }
    if not legs:
        result["reason"] = "No verified mixed-sport alternate combination reached the +450 to +600 target."
    elif not target_reached:
        result["reason"] = (
            "No verified combination landed inside +450 to +600; showing the "
            "closest available alternate-line combination instead."
        )
    os.makedirs("logs", exist_ok=True)
    path = f"logs/{scrape_date}_cross_sport_parlay.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
    print(
        f"🎰 Cross-sport alt parlay: {len(legs)} leg(s), "
        f"{('+' + str(combined_american)) if combined_american is not None and combined_american > 0 else combined_american or 'unavailable'}"
    )
    print(f"💾 Cross-sport parlay saved to {path}")
    return result


if __name__ == "__main__":
    import sys
    build_cross_sport_parlay(sys.argv[1] if len(sys.argv) > 1 else None)
