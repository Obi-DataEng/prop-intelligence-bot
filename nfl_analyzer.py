import os
import sys
import json
import re
from glob import glob
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from anthropic import Anthropic

from news_fetcher import (
    load_news,
    format_news_for_prompt,
)

load_dotenv()


# ============================================================
# CONFIG
# ============================================================

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

NFL_MODEL = os.getenv(
    "NFL_MODEL",
    "claude-sonnet-4-5",
)



MIN_CONFIDENCE = 72
MAX_PICKS = 5

VALID_BOOKS = {
    "FD": "FanDuel",
    "CZS": "Caesars",
}

NFL_TEAM_ABBREVIATIONS = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL", "Denver Broncos": "DEN",
    "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX", "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA", "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN", "New England Patriots": "NE",
    "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT", "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}


# ============================================================
# HELPERS
# ============================================================

def ensure_anthropic_key():
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "Missing ANTHROPIC_API_KEY in .env"
        )


def normalize_text(value):
    """
    Normalize strings for matching.
    """
    if value is None:
        return ""

    value = str(value).lower().strip()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def lines_match(a, b, tolerance=0.001):
    """
    Compare betting lines safely.
    """
    if a is None or b is None:
        return False

    try:
        return abs(
            float(a) - float(b)
        ) <= tolerance

    except (
        TypeError,
        ValueError,
    ):
        return False


def confidence_tier(score):
    """
    Deterministic confidence tiers.

    88+ = Elite
    80-87 = High
    72-79 = Medium
    <72 = Below Threshold
    """
    try:
        score = float(score)
    except (
        TypeError,
        ValueError,
    ):
        return "Below Threshold"

    if score >= 88:
        return "Elite"

    if score >= 80:
        return "High"

    if score >= 72:
        return "Medium"

    return "Below Threshold"


def best_american_price(prices):
    """
    For American odds, the numerically largest
    price is best for the bettor.

    Examples:
      +120 beats +110
      -105 beats -110
      +100 beats -105
    """
    if not prices:
        return None

    return max(
        prices,
        key=lambda x: x["odds"],
    )


# ============================================================
# LOAD ODDS
# ============================================================

def load_nfl_odds(scrape_date):
    filepath = resolve_log_snapshot(scrape_date, "nfl_odds")

    if filepath is None:
        raise FileNotFoundError(
            f"NFL odds file not found for or before {scrape_date}"
        )

    if not filepath.endswith(f"{scrape_date}_nfl_odds.json"):
        print(f"ℹ️ Using latest odds snapshot: {filepath}")

    with open(
        filepath,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def resolve_log_snapshot(target_date, suffix):
    """Return exact or newest prior YYYY-MM-DD log snapshot."""
    exact = f"logs/{target_date}_{suffix}.json"
    if os.path.exists(exact):
        return exact

    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    candidates = []
    for filepath in glob(f"logs/????-??-??_{suffix}.json"):
        filename = os.path.basename(filepath)
        try:
            file_date = datetime.strptime(filename[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date <= target:
            candidates.append((file_date, filepath))
    return max(candidates, default=(None, None))[1]


def load_snapshot_if_exists(target_date, suffix, default):
    filepath = resolve_log_snapshot(target_date, suffix)
    if filepath is None:
        return default
    if not filepath.endswith(f"{target_date}_{suffix}.json"):
        print(f"ℹ️ Using latest {suffix} snapshot: {filepath}")
    with open(filepath, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_nfl_intelligence(scrape_date):
    """Load every PropFinder NFL source produced by scraper.py nfl."""
    return {
        "props": load_snapshot_if_exists(
            scrape_date, "nfl_props", {"views": {}}
        ),
        "games": load_snapshot_if_exists(
            scrape_date, "nfl_games", {"cards": []}
        ),
        "weather": load_snapshot_if_exists(
            scrape_date, "nfl_weather", {"blocks": []}
        ),
        "home_field": load_snapshot_if_exists(
            scrape_date, "nfl_home_field_advantage", {"blocks": []}
        ),
        "discrepancies": load_snapshot_if_exists(
            scrape_date, "nfl_odds_discrepancies", {"html_rows": []}
        ),
    }


def nfl_week_from_intelligence(intelligence):
    """Read the displayed week, defaulting conservatively to Week 1."""
    for source in ("games", "weather"):
        text = intelligence.get(source, {}).get("fullText", "")
        match = re.search(r"\bWeek\s+(\d{1,2})\b", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 1


def season_weights(week):
    if week <= 2:
        return 0.70, 0.30
    if week <= 4:
        return 0.40, 0.60
    return 0.15, 0.85


def teams_on_prop_finder_slate(game_cards, target_date):
    """Extract PropFinder team abbreviations for the requested game date."""
    target = datetime.strptime(target_date, "%Y-%m-%d")
    target_label = target.strftime("%b %d").replace(" 0", " ").lower()
    teams = set()

    for card in game_cards:
        kickoff_index = None
        for index, value in enumerate(card):
            normalized = str(value).lower().replace(",", "")
            if target_label in normalized:
                kickoff_index = index
                break
        if kickoff_index is None:
            continue

        for value in card[1:kickoff_index]:
            token = str(value).strip()
            if re.fullmatch(r"[A-Z][A-Z0-9-]{1,6}", token):
                teams.add(token)

    return teams


def teams_in_odds_slate(games):
    """Return PropFinder abbreviations for the exact filtered Odds API slate."""
    teams = set()
    for game in games:
        for key in ("home_team", "away_team"):
            abbreviation = NFL_TEAM_ABBREVIATIONS.get(game.get(key, ""))
            if abbreviation:
                teams.add(abbreviation)
    return teams


def build_prop_finder_model_index(game_cards):
    """Normalize projected scores and win probabilities by NFL team pair."""
    index = {}
    for card in game_cards:
        if not isinstance(card, list) or len(card) < 9:
            continue
        away_abbr = str(card[1]).strip()
        home_abbr = str(card[3]).strip()
        try:
            away_score = float(card[2])
            home_score = float(card[4])
        except (TypeError, ValueError):
            continue

        win_probabilities = {}
        model_spreads = {}
        precise_total = None
        for value in card[6:12]:
            match = re.search(r"\b([A-Z]{2,3})\s+(\d+(?:\.\d+)?)%", str(value))
            if match:
                win_probabilities[match.group(1)] = float(match.group(2)) / 100

        for value in card:
            text = str(value).replace("−", "-")
            spread_match = re.search(
                r"\bModel\s+([A-Z]{2,3})\s+([+-]\d+(?:\.\d+)?)", text
            )
            if spread_match:
                model_spreads[spread_match.group(1)] = float(spread_match.group(2))
            total_match = re.search(r"\bModel\s+(\d+(?:\.\d+)?)\s*[·+-]", text)
            if total_match:
                precise_total = float(total_match.group(1))

        if away_abbr in model_spreads and home_abbr not in model_spreads:
            model_spreads[home_abbr] = -model_spreads[away_abbr]
        if home_abbr in model_spreads and away_abbr not in model_spreads:
            model_spreads[away_abbr] = -model_spreads[home_abbr]

        index[frozenset((away_abbr, home_abbr))] = {
            "away_abbr": away_abbr,
            "home_abbr": home_abbr,
            "away_score": away_score,
            "home_score": home_score,
            "projected_total": precise_total or (away_score + home_score),
            "win_probabilities": win_probabilities,
            "model_spreads": model_spreads,
        }
    return index


def model_for_odds_game(game, model_index):
    away = NFL_TEAM_ABBREVIATIONS.get(game.get("away_team", ""))
    home = NFL_TEAM_ABBREVIATIONS.get(game.get("home_team", ""))
    if not away or not home:
        return None
    return model_index.get(frozenset((away, home)))


def american_implied_probability(odds):
    odds = float(odds)
    return (-odds / (-odds + 100)) if odds < 0 else (100 / (odds + 100))


def parse_hit_rate(value):
    match = re.search(r"(\d+)\s*/\s*(\d+)", str(value or ""))
    if not match:
        return 0, 0, 0.0
    hits, games = int(match.group(1)), int(match.group(2))
    return hits, games, (hits / games if games else 0.0)


def parse_prop_label(value):
    match = re.match(
        r"^\s*([ou])\s*(-?\d+(?:\.\d+)?)\s+(.+?)\s*$",
        str(value or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return {
        "direction": "Over" if match.group(1).lower() == "o" else "Under",
        "line": float(match.group(2)),
        "market": match.group(3).strip(),
    }


def safe_float(value, default=0.0):
    try:
        return float(str(value).replace("−", "-").replace("+", ""))
    except (TypeError, ValueError):
        return default


def build_prop_candidates(props_data, eligible_teams=None, limit=25, week=1):
    """Deterministically rank complete PropFinder export rows."""
    candidates = []
    seen = set()

    for view in props_data.get("views", {}).values():
        for row in view.get("rows", []):
            if not isinstance(row, dict):
                continue
            parsed = parse_prop_label(row.get("Prop"))
            if not parsed:
                continue
            player = str(row.get("Player", "")).strip()
            team = str(row.get("Team", "")).strip()
            if not player or not team:
                continue
            if eligible_teams is not None and team not in eligible_teams:
                continue

            odds = int(round(safe_float(row.get("Odds"), -9999)))
            # Avoid extreme pricing and low-information records.
            if odds < -200 or odds > 300:
                continue

            _, l10_n, l10_rate = parse_hit_rate(row.get("L10"))
            _, l20_n, l20_rate = parse_hit_rate(row.get("L20"))
            if l10_n < 5 or l20_n < 5:
                continue

            pf_rating = safe_float(row.get("PF Rating"))
            if pf_rating < MIN_CONFIDENCE:
                continue

            season_columns = [
                key for key in row
                if len(re.findall(r"\d{2}", str(key))) == 2
                and "-" in str(key)
            ]
            season_columns.sort()
            prior_value = row.get(season_columns[-2]) if len(season_columns) >= 2 else None
            current_value = row.get(season_columns[-1]) if season_columns else None
            _, prior_n, prior_rate = parse_hit_rate(prior_value)
            _, current_n, current_rate = parse_hit_rate(current_value)
            prior_weight, current_weight = season_weights(week)

            weighted_parts = []
            if prior_n:
                weighted_parts.append((prior_rate, prior_weight))
            if current_n:
                weighted_parts.append((current_rate, current_weight))
            season_rate = (
                sum(rate * weight for rate, weight in weighted_parts) /
                sum(weight for _, weight in weighted_parts)
                if weighted_parts else l20_rate
            )

            price_score = min(100.0, max(0.0, 100 - max(0, -odds - 100) * 0.35))
            confidence = int(round(min(
                92,
                (pf_rating * 0.45) +
                (season_rate * 100 * 0.30) +
                (l10_rate * 100 * 0.15) +
                (price_score * 0.10),
            )))
            # With no current-season sample, do not call historical evidence
            # an elite current-season edge.
            if current_n == 0:
                confidence = min(confidence, 87)

            key = (
                normalize_text(player), normalize_text(team),
                parsed["direction"], parsed["line"],
                normalize_text(parsed["market"]),
            )
            if key in seen:
                continue
            seen.add(key)

            candidates.append({
                "rank": 0,
                "pick_type": "player_prop",
                "game": f"{team} game",
                "team": team,
                "player": player,
                "market": parsed["market"],
                "selection": (
                    f"{player} {parsed['direction']} "
                    f"{parsed['line']:g} {parsed['market']}"
                ),
                "line": parsed["line"],
                "over_under": parsed["direction"],
                "best_book": "PropFinder",
                "best_odds": odds,
                "prediction_confidence": confidence,
                "confidence_tier": confidence_tier(confidence),
                "pf_rating": pf_rating,
                "l10_average": safe_float(row.get("L10 Avg")),
                "l10_hit_rate": row.get("L10"),
                "l20_hit_rate": row.get("L20"),
                "season_matchup_rank": row.get("SZN Matchup"),
                "nfl_week": week,
                "prior_season_hit_rate": prior_value,
                "current_season_hit_rate": current_value,
                "prior_season_weight": prior_weight,
                "current_season_weight": current_weight,
                "current_season_sample": current_n,
                "historical_only": current_n == 0,
                "reasoning": (
                    f"PropFinder rating {pf_rating:.1f}; "
                    f"L10 {row.get('L10')} and L20 {row.get('L20')}; "
                    f"prior/current season {prior_value or 'N/A'} / "
                    f"{current_value or 'N/A'} with Week {week} weighting "
                    f"{prior_weight:.0%}/{current_weight:.0%}; "
                    f"L10 average {row.get('L10 Avg')} at odds {odds:+d}."
                ),
            })

    candidates.sort(
        key=lambda item: (
            item["prediction_confidence"], item["pf_rating"],
            item["best_odds"],
        ),
        reverse=True,
    )
    return candidates[:limit]


def format_prop_finder_context(intelligence, slate_games):
    """Return context restricted to teams in the exact Odds API slate."""
    eligible_pairs = set()
    home_names = []
    slate_matchups = []
    for game in slate_games:
        away = NFL_TEAM_ABBREVIATIONS.get(game.get("away_team", ""))
        home = NFL_TEAM_ABBREVIATIONS.get(game.get("home_team", ""))
        if away and home:
            eligible_pairs.add(frozenset((away, home)))
        home_names.append(normalize_text(game.get("home_team", "")))
        slate_matchups.append((
            normalize_text(game.get("away_team", "")),
            normalize_text(game.get("home_team", "")),
        ))

    cards = intelligence.get("games", {}).get("cards", [])
    selected_cards = [
        card for card in cards
        if isinstance(card, list) and len(card) >= 4
        and frozenset((str(card[1]).strip(), str(card[3]).strip())) in eligible_pairs
    ]
    game_lines = [" | ".join(map(str, card)) for card in selected_cards]

    home_blocks = intelligence.get("home_field", {}).get("blocks", [])
    selected_home_blocks = []
    selected_stadiums = set()
    for block in home_blocks:
        if not isinstance(block, list) or not block or not str(block[0]).startswith("#"):
            continue
        if "former venue" in normalize_text(" ".join(map(str, block))):
            continue
        block_text = normalize_text(" ".join(map(str, block)))
        if any(
            home and (
                home in block_text
                or home.split()[-1] in normalize_text(str(block[1] if len(block) > 1 else ""))
            )
            for home in home_names
        ):
            selected_home_blocks.append(block)
            if len(block) > 3:
                selected_stadiums.add(normalize_text(block[3]))

    weather_blocks = intelligence.get("weather", {}).get("blocks", [])
    weather_lines = [
        " | ".join(map(str, block)) for block in weather_blocks
        if isinstance(block, list)
        and any(stadium and stadium in normalize_text(" ".join(map(str, block)))
                for stadium in selected_stadiums)
        and any(
            away in normalize_text(" ".join(map(str, block)))
            and home in normalize_text(" ".join(map(str, block)))
            for away, home in slate_matchups
        )
    ]

    home_lines = [
        " | ".join(map(str, block)) for block in selected_home_blocks
    ]

    return (
        "EXACT-SLATE PROPFINDER GAMES & PROJECTIONS:\n" +
        ("\n".join(game_lines) or "No matching projection card.") +
        "\n\nEXACT-SLATE WEATHER:\n" +
        ("\n".join(weather_lines) or "No material or joinable weather record.") +
        "\n\nEXACT-SLATE HOME-FIELD HISTORY "
        "(rank, team, venue type/stadium, games, record, win%, "
        "average margin, average vs spread):\n" +
        ("\n".join(home_lines) or "No matching home-field record.")
    )


# ============================================================
# FILTER CURRENT NFL SLATE
# ============================================================

def parse_commence_time(value):
    """
    Convert The Odds API ISO timestamp to datetime.
    """
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:
        return None


def filter_nfl_slate(
    games,
    scrape_date,
):
    """
    Keep ONLY NFL games occurring on scrape_date
    in Eastern Time.

    This keeps NFL aligned with the MLB/NBA/WNBA
    daily betting slate.
    """
    eastern = ZoneInfo(
        "America/New_York"
    )

    target_date = datetime.strptime(
        scrape_date,
        "%Y-%m-%d",
    ).date()

    filtered = []

    for game in games:
        commence = parse_commence_time(
            game.get("commence_time")
        )

        if commence is None:
            continue

        eastern_time = commence.astimezone(
            eastern
        )

        if eastern_time.date() == target_date:
            filtered.append(game)

    filtered.sort(
        key=lambda game: (
            game.get(
                "commence_time",
                "",
            )
        )
    )

    return filtered


# ============================================================
# FORMAT ODDS FOR CLAUDE
# ============================================================

def format_nfl_odds_for_prompt(games):
    """
    Convert NFL sportsbook data into compact,
    readable prompt text.
    """
    if not games:
        return "No NFL games available."

    sections = []

    for game in games:
        away = game.get(
            "away_team",
            "",
        )

        home = game.get(
            "home_team",
            "",
        )

        commence = game.get(
            "commence_time",
            "",
        )

        lines = [
            f"{away} @ {home}",
            f"Start: {commence}",
        ]

        bookmakers = game.get(
            "bookmakers",
            {},
        )

        for book in [
            "FD",
            "CZS",
        ]:
            odds = bookmakers.get(book)

            if not odds:
                continue

            lines.append(
                (
                    f"{book}: "
                    f"away_ml={odds.get('away_ml')} | "
                    f"home_ml={odds.get('home_ml')} | "
                    f"away_spread={odds.get('away_spread')} "
                    f"({odds.get('away_spread_odds')}) | "
                    f"home_spread={odds.get('home_spread')} "
                    f"({odds.get('home_spread_odds')}) | "
                    f"total={odds.get('total')} | "
                    f"over={odds.get('over_odds')} | "
                    f"under={odds.get('under_odds')}"
                )
            )

        sections.append(
            "\n".join(lines)
        )

    return "\n\n".join(
        sections
    )


# ============================================================
# CLAUDE PROMPT
# ============================================================

def build_nfl_prompt(
    games,
    news_data,
    scrape_date,
    propfinder_context="",
):
    odds_text = format_nfl_odds_for_prompt(
        games
    )

    news_text = format_news_for_prompt(
        news_data,
        "NFL",
    )

    return f"""
You are a disciplined NFL betting analyst.

DATE:
{scrape_date}

============================================================
STRICT SCOPE
============================================================

PLAYER PROPS ARE SCORED SEPARATELY BY PYTHON.

Do not analyze, recommend, rank, mention, or create player props
in this response. Select game bets only; Python builds a separate
Top 5 player-prop list from the complete PropFinder export.

The ONLY eligible betting markets are:

1. Moneyline
2. Spread
3. Game total

Do not recommend first-half markets.
Do not recommend team totals.
Do not recommend futures.
Do not recommend parlays.

============================================================
OBJECTIVE
============================================================

Evaluate the entire supplied NFL slate and identify the
strongest betting opportunities across moneylines,
spreads, and game totals.

Rank all eligible markets together.

Return the {MAX_PICKS} strongest betting candidates from the supplied slate,
ranked from strongest to weakest.

Evaluate moneylines, spreads, and game totals across all games.

Assign each candidate an honest confidence score from 0-100.

Do NOT artificially increase confidence.

Python will independently determine which candidates officially
qualify as bets.

Whenever at least {MAX_PICKS} eligible markets exist in the supplied slate,
return {MAX_PICKS} candidates even if some have confidence below the official
betting threshold.

If fewer than {MAX_PICKS} eligible markets exist, return all eligible candidates.

Never force five picks from a small slate. There are at most three independent
game markets per matchup: one moneyline, one spread side, and one total side.
Never return both teams against the same spread, and never return both Over and
Under on the same total. Do not select a side when the supplied model projection
opposes it. A moneyline must have model win probability at least two percentage
points above the price's implied probability.

============================================================
CONFIDENCE
============================================================

The official betting threshold is {MIN_CONFIDENCE}.

However, return your strongest candidates even when their confidence
is below {MIN_CONFIDENCE}. Python will reject candidates that fail
the official threshold.

Confidence scale:

88-100 = Elite
80-87 = High
72-79 = Medium
Below 72 = DO NOT RETURN

Do not inflate confidence.

A betting market merely having a sportsbook line is not
evidence that it is a good bet.

============================================================
EVIDENCE PRIORITY
============================================================

Prioritize relevant evidence such as:

- current injuries
- quarterback availability
- offensive line availability
- major defensive absences
- depth-chart changes
- matchup strengths and weaknesses
- offensive efficiency
- defensive efficiency
- pace/style
- returning production and offseason personnel changes
- coaching/system changes
- recent team-specific reporting
- home/road context
- neutral-site context
- meaningful market disagreement between books

News articles may contain generic NFL content.

Down-weight or ignore articles that are not directly
relevant to the teams, matchup, personnel, injuries,
coaching, or game conditions.

Do not treat generic rankings, coach salaries,
conference predictions, or unrelated national stories
as meaningful betting evidence.

============================================================
SPORTSBOOK RULES
============================================================

Only these books exist for this analysis:

FD = FanDuel
CZS = Caesars

Use ONLY lines supplied below.

The matchups listed in NFL ODDS are the complete and exclusive slate.
Never select a game that is absent from NFL ODDS, even if it appears in news
or supporting context.

Never invent:

- a sportsbook
- a moneyline price
- a spread
- a spread price
- a total
- a total price

For spreads and totals, the EXACT line matters.

For example:

FanDuel -6.5 and Caesars -7 are NOT the same bet.

Do not claim one book has a better price unless the exact
same side and exact same line are available there.

Python will independently verify every recommendation
after your analysis.

============================================================
SELECTION RULES
============================================================

MONEYLINE:

- pick_type must be "moneyline"
- team must be the selected team
- line must be null
- over_under must be null

SPREAD:

- pick_type must be "spread"
- team must be the selected team
- line must exactly equal that team's spread
- over_under must be null

GAME TOTAL:

- pick_type must be "game_total"
- team must be null
- line must exactly equal the sportsbook total
- over_under must be exactly "Over" or "Under"

============================================================
NFL ODDS
============================================================

{odds_text}

============================================================
PROPFINDER TEAM MODEL CONTEXT
============================================================

Use this only as supporting evidence for moneyline, spread, and game-total
decisions. Sportsbook validation still uses the NFL ODDS section above.

{propfinder_context}

============================================================
RECENT NEWS / CONTEXT
============================================================

{news_text}

============================================================
OUTPUT FORMAT
============================================================

Return VALID JSON ONLY.

Do not use markdown.

Do not use ```json fences.

Use this exact structure:

{{
  "analysis_date": "{scrape_date}",
  "league": "NFL",
  "picks": [
    {{
      "rank": 1,
      "pick_type": "spread",
      "game": "Away Team @ Home Team",
      "team": "Selected Team",
      "selection": "Selected Team +7.5",
      "line": 7.5,
      "over_under": null,
      "best_book": "FD",
      "best_odds": -110,
      "prediction_confidence": 82,
      "confidence_tier": "High",
      "reasoning": "Concise betting rationale based only on available evidence."
    }}
  ]
}}

Moneyline example:

{{
  "rank": 1,
  "pick_type": "moneyline",
  "game": "Away Team @ Home Team",
  "team": "Selected Team",
  "selection": "Selected Team moneyline",
  "line": null,
  "over_under": null,
  "best_book": "CZS",
  "best_odds": 125,
  "prediction_confidence": 80,
  "confidence_tier": "High",
  "reasoning": "..."
}}

Game-total example:

{{
  "rank": 1,
  "pick_type": "game_total",
  "game": "Away Team @ Home Team",
  "team": null,
  "selection": "Under 47.5",
  "line": 47.5,
  "over_under": "Under",
  "best_book": "FD",
  "best_odds": -105,
  "prediction_confidence": 78,
  "confidence_tier": "Medium",
  "reasoning": "..."
}}

Return JSON only.
"""


# ============================================================
# CALL CLAUDE
# ============================================================

def extract_json(text):
    """
    Clean accidental markdown fences and recover JSON.
    """
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"```$",
            "",
            text,
        )

        text = text.strip()

    try:
        return json.loads(text)

    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")

        if (
            start == -1
            or end == -1
            or end <= start
        ):
            raise

        return json.loads(
            text[start:end + 1]
        )


def analyze_with_claude(
    games,
    news_data,
    scrape_date,
    propfinder_context="",
):
    ensure_anthropic_key()

    client = Anthropic(
        api_key=ANTHROPIC_API_KEY
    )

    prompt = build_nfl_prompt(
        games,
        news_data,
        scrape_date,
        propfinder_context,
    )

    print(
        "\n🧠 Sending NFL slate to Claude..."
    )

    print(
        f"   🎮 Games in analysis: "
        f"{len(games)}"
    )

    response = client.messages.create(
        model=NFL_MODEL,
        max_tokens=5000,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    text_parts = []

    for block in response.content:
        if hasattr(
            block,
            "text",
        ):
            text_parts.append(
                block.text
            )

    raw_text = "".join(
        text_parts
    ).strip()

    print("\n📝 RAW CLAUDE NFL RESPONSE:")
    print(raw_text)
    print()

    if not raw_text:
        raise RuntimeError(
            "Claude returned an empty response."
        )

    return extract_json(
        raw_text
    )


# ============================================================
# GAME MATCHING
# ============================================================

def find_game_for_pick(
    pick,
    games,
):
    """
    Match Claude's game to an actual odds game.
    """
    requested_game = normalize_text(
        pick.get("game")
    )

    requested_team = normalize_text(
        pick.get("team")
    )

    # First try the exact game string.
    if requested_game:
        for game in games:
            actual = normalize_text(
                (
                    f"{game.get('away_team', '')} "
                    f"@ "
                    f"{game.get('home_team', '')}"
                )
            )

            if actual == requested_game:
                return game

    # Fallback for ML/spread:
    # locate game containing selected team.
    if requested_team:
        matches = []

        for game in games:
            home = normalize_text(
                game.get(
                    "home_team",
                )
            )

            away = normalize_text(
                game.get(
                    "away_team",
                )
            )

            if requested_team in {
                home,
                away,
            }:
                matches.append(game)

        if len(matches) == 1:
            return matches[0]

    return None


def team_side(
    team,
    game,
):
    """
    Determine whether selected team is home or away.
    """
    selected = normalize_text(team)

    home = normalize_text(
        game.get(
            "home_team",
        )
    )

    away = normalize_text(
        game.get(
            "away_team",
        )
    )

    if selected == home:
        return "home"

    if selected == away:
        return "away"

    return None


# ============================================================
# VALIDATE MONEYLINE
# ============================================================

def validate_moneyline(
    pick,
    game,
):
    selected_team = pick.get(
        "team"
    )

    side = team_side(
        selected_team,
        game,
    )

    if side is None:
        return None, (
            "selected moneyline team "
            "does not match game"
        )

    prices = []

    for book, odds in game.get(
        "bookmakers",
        {},
    ).items():

        if book not in VALID_BOOKS:
            continue

        price = odds.get(
            f"{side}_ml"
        )

        if price is None:
            continue

        try:
            price = int(price)
        except (
            TypeError,
            ValueError,
        ):
            continue

        prices.append(
            {
                "book": book,
                "odds": price,
            }
        )

    best = best_american_price(
        prices
    )

    if best is None:
        return None, (
            "moneyline not available "
            "at FD or Caesars"
        )

    validated = dict(pick)

    validated["team"] = (
        game["home_team"]
        if side == "home"
        else game["away_team"]
    )

    validated["line"] = None
    validated["over_under"] = None
    validated["best_book"] = best["book"]
    validated["best_odds"] = best["odds"]

    validated["selection"] = (
        f"{validated['team']} moneyline"
    )

    return validated, None


# ============================================================
# VALIDATE SPREAD
# ============================================================

def validate_spread(
    pick,
    game,
):
    selected_team = pick.get(
        "team"
    )

    requested_line = pick.get(
        "line"
    )

    side = team_side(
        selected_team,
        game,
    )

    if side is None:
        return None, (
            "selected spread team "
            "does not match game"
        )

    if requested_line is None:
        return None, (
            "spread pick missing line"
        )

    exact_matches = []

    for book, odds in game.get(
        "bookmakers",
        {},
    ).items():

        if book not in VALID_BOOKS:
            continue

        book_line = odds.get(
            f"{side}_spread"
        )

        book_price = odds.get(
            f"{side}_spread_odds"
        )

        if (
            book_line is None
            or book_price is None
        ):
            continue

        if not lines_match(
            requested_line,
            book_line,
        ):
            continue

        try:
            price = int(
                book_price
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        exact_matches.append(
            {
                "book": book,
                "line": float(
                    book_line
                ),
                "odds": price,
            }
        )

    best = best_american_price(
        exact_matches
    )

    if best is None:
        return None, (
            f"exact spread line "
            f"{requested_line} "
            f"not available"
        )

    validated = dict(pick)

    actual_team = (
        game["home_team"]
        if side == "home"
        else game["away_team"]
    )

    validated["team"] = actual_team
    validated["line"] = best["line"]
    validated["over_under"] = None
    validated["best_book"] = best["book"]
    validated["best_odds"] = best["odds"]

    line = best["line"]

    line_display = (
        f"+{line:g}"
        if line > 0
        else f"{line:g}"
    )

    validated["selection"] = (
        f"{actual_team} "
        f"{line_display}"
    )

    return validated, None


# ============================================================
# VALIDATE GAME TOTAL
# ============================================================

def validate_game_total(
    pick,
    game,
):
    requested_line = pick.get(
        "line"
    )

    requested_side = str(
        pick.get(
            "over_under",
            "",
        )
    ).strip().lower()

    if requested_side not in {
        "over",
        "under",
    }:
        return None, (
            "game total must specify "
            "Over or Under"
        )

    if requested_line is None:
        return None, (
            "game total missing line"
        )

    exact_matches = []

    for book, odds in game.get(
        "bookmakers",
        {},
    ).items():

        if book not in VALID_BOOKS:
            continue

        book_total = odds.get(
            "total"
        )

        if not lines_match(
            requested_line,
            book_total,
        ):
            continue

        price_key = (
            "over_odds"
            if requested_side == "over"
            else "under_odds"
        )

        book_price = odds.get(
            price_key
        )

        if book_price is None:
            continue

        try:
            price = int(
                book_price
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        exact_matches.append(
            {
                "book": book,
                "line": float(
                    book_total
                ),
                "odds": price,
            }
        )

    best = best_american_price(
        exact_matches
    )

    if best is None:
        return None, (
            f"exact total line "
            f"{requested_line} "
            f"not available"
        )

    validated = dict(pick)

    proper_side = (
        "Over"
        if requested_side == "over"
        else "Under"
    )

    validated["team"] = None
    validated["line"] = best["line"]
    validated["over_under"] = proper_side
    validated["best_book"] = best["book"]
    validated["best_odds"] = best["odds"]

    validated["selection"] = (
        f"{proper_side} "
        f"{best['line']:g}"
    )

    return validated, None


def validate_model_edge(checked, game, model_index):
    """Require the PropFinder projection to support the selected side."""
    model = model_for_odds_game(game, model_index or {})
    if model is None:
        return None, "no matching PropFinder projection for edge validation"

    pick_type = checked.get("pick_type")
    if pick_type == "moneyline":
        team = checked.get("team")
        abbreviation = NFL_TEAM_ABBREVIATIONS.get(team)
        model_probability = model["win_probabilities"].get(abbreviation)
        if model_probability is None:
            return None, "PropFinder win probability unavailable"
        implied = american_implied_probability(checked["best_odds"])
        edge = model_probability - implied
        if edge < 0.02:
            return None, (
                f"moneyline has no qualifying value: model {model_probability:.1%} "
                f"vs implied {implied:.1%} ({edge:+.1%} edge)"
            )
        checked["model_probability"] = round(model_probability, 4)
        checked["implied_probability"] = round(implied, 4)
        checked["model_edge"] = round(edge, 4)

    elif pick_type == "spread":
        selected = NFL_TEAM_ABBREVIATIONS.get(checked.get("team"))
        if selected in model.get("model_spreads", {}):
            projected_margin = -model["model_spreads"][selected]
        elif selected == model["away_abbr"]:
            projected_margin = model["away_score"] - model["home_score"]
        elif selected == model["home_abbr"]:
            projected_margin = model["home_score"] - model["away_score"]
        else:
            return None, "selected team missing from PropFinder projection"
        edge = projected_margin + float(checked["line"])
        if edge < 0.5:
            return None, f"spread is not supported by projection ({edge:+.1f} point edge)"
        checked["projected_margin"] = round(projected_margin, 2)
        checked["model_edge"] = round(edge, 2)

    elif pick_type == "game_total":
        line = float(checked["line"])
        projected = model["projected_total"]
        edge = projected - line
        if checked.get("over_under") == "Under":
            edge = -edge
        if edge < 0.5:
            return None, f"total side is not supported by projection ({edge:+.1f} point edge)"
        checked["projected_total"] = round(projected, 2)
        checked["model_edge"] = round(edge, 2)

    return checked, None


# ============================================================
# VALIDATE ALL CLAUDE PICKS
# ============================================================

def validate_nfl_picks(
    claude_data,
    games,
    model_index=None,
):
    print(
        "\n🔎 Validating Claude NFL picks "
        "against FD/Caesars..."
    )

    raw_picks = claude_data.get(
        "picks",
        [],
    )

    if not isinstance(
        raw_picks,
        list,
    ):
        raw_picks = []

    validated = []
    rejected = []
    used_markets = set()

    for index, pick in enumerate(
        raw_picks,
        start=1,
    ):
        if not isinstance(
            pick,
            dict,
        ):
            rejected.append(
                {
                    "pick": pick,
                    "reason": (
                        "pick is not an object"
                    ),
                }
            )
            continue

        confidence = pick.get(
            "prediction_confidence",
            pick.get(
                "confidence_score",
                0,
            ),
        )

        try:
            confidence = int(
                round(
                    float(confidence)
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            confidence = 0

        if confidence < MIN_CONFIDENCE:
            rejected.append(
                {
                    "pick": pick,
                    "reason": (
                        f"confidence {confidence} "
                        f"is below "
                        f"{MIN_CONFIDENCE}"
                    ),
                }
            )
            continue

        game = find_game_for_pick(
            pick,
            games,
        )

        if game is None:
            rejected.append(
                {
                    "pick": pick,
                    "reason": (
                        "could not match game "
                        "to odds feed"
                    ),
                }
            )
            continue

        pick_type = normalize_text(
            pick.get(
                "pick_type",
            )
        ).replace(
            " ",
            "_",
        )

        if pick_type == "moneyline":
            checked, error = (
                validate_moneyline(
                    pick,
                    game,
                )
            )

        elif pick_type == "spread":
            checked, error = (
                validate_spread(
                    pick,
                    game,
                )
            )

        elif pick_type in {
            "game_total",
            "total",
        }:
            checked, error = (
                validate_game_total(
                    pick,
                    game,
                )
            )

            if checked:
                checked[
                    "pick_type"
                ] = "game_total"

        else:
            checked = None

            error = (
                f"unsupported market: "
                f"{pick.get('pick_type')}"
            )

        if checked is None:
            rejected.append(
                {
                    "pick": pick,
                    "reason": error,
                }
            )
            continue

        checked, error = validate_model_edge(
            checked, game, model_index or {}
        )
        if checked is None:
            rejected.append({"pick": pick, "reason": error})
            continue

        game_key = normalize_text(
            f"{game['away_team']} @ {game['home_team']}"
        )
        market_key = (game_key, checked.get("pick_type"))
        if market_key in used_markets:
            rejected.append({
                "pick": pick,
                "reason": "duplicate or opposing side already selected for this game/market",
            })
            continue
        used_markets.add(market_key)

        checked[
            "prediction_confidence"
        ] = confidence

        checked[
            "confidence_tier"
        ] = confidence_tier(
            confidence
        )

        checked["game"] = (
            f"{game['away_team']} "
            f"@ "
            f"{game['home_team']}"
        )

        # Preserve Claude's original order.
        checked["rank"] = (
            len(validated) + 1
        )

        validated.append(
            checked
        )

        if (
            len(validated)
            >= MAX_PICKS
        ):
            break

    print(
        f"   ✅ {len(validated)} validated"
        f" | ❌ {len(rejected)} rejected"
    )

    for item in rejected:
        selection = (
            item.get(
                "pick",
                {},
            ).get(
                "selection",
                "Unknown pick",
            )
            if isinstance(
                item.get("pick"),
                dict,
            )
            else "Unknown pick"
        )

        print(
            f"   ❌ {selection}: "
            f"{item['reason']}"
        )

    return (
        validated,
        rejected,
    )


# ============================================================
# SAVE RESULTS
# ============================================================

def save_nfl_picks(
    scrape_date,
    games,
    validated,
    rejected,
    props_analyzed=0,
):
    player_prop_picks = [
        pick for pick in validated
        if pick.get("pick_type") == "player_prop"
    ]
    game_picks = [
        pick for pick in validated
        if pick.get("pick_type") != "player_prop"
    ]

    output = {
        "date": scrape_date,
        "league": "NFL",
        "markets": [
            "moneyline",
            "spread",
            "game_total",
            "player_prop",
        ],
        "player_props_enabled": True,
        "books": [
            "FD",
            "CZS",
            "PropFinder (player-prop price source; book name unavailable in CSV)",
        ],
        "games_analyzed": len(games),
        "props_analyzed": props_analyzed,
        "player_prop_picks": player_prop_picks,
        "game_picks": game_picks,
        "picks": validated,
        "rejected_picks": rejected,
    }

    os.makedirs(
        "logs",
        exist_ok=True,
    )

    filepath = (
        f"logs/{scrape_date}_"
        f"nfl_picks.json"
    )

    with open(
        filepath,
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
        f"\n💾 NFL picks saved to "
        f"{filepath}"
    )

    return output


# ============================================================
# DISPLAY
# ============================================================

def print_nfl_results(
    picks,
):
    print(
        "\n"
        + "=" * 65
    )

    print("🏈 NFL VALIDATED PICKS — TWO SEPARATE TOP 5 LISTS")

    print(
        "=" * 65
    )

    if not picks:
        print(
            "\nNo NFL bets cleared "
            "the validation threshold."
        )

        return

    prop_picks = [
        pick for pick in picks
        if pick.get("pick_type") == "player_prop"
    ]
    game_picks = [
        pick for pick in picks
        if pick.get("pick_type") != "player_prop"
    ]

    for heading, group in [
        ("🏃 TOP PLAYER PROPS", prop_picks),
        ("🎮 TOP GAME PICKS — ML / SPREAD / O-U", game_picks),
    ]:
        print(f"\n{heading}")
        print("-" * 65)
        if not group:
            print("No qualifying picks in this category.")
            continue

        for pick in group:
            rank = pick.get("rank", "")

            tier = pick.get("confidence_tier", "")

            confidence = pick.get("prediction_confidence", "")

            selection = pick.get("selection", "")

            book = pick.get("best_book", "")

            odds = pick.get("best_odds", "")

            game = pick.get("game", "")

            reasoning = pick.get("reasoning", "")

            if isinstance(odds, (int, float)) and odds > 0:
                odds_display = f"+{odds}"

            else:
                odds_display = str(odds)

            print(f"\n#{rank} [{tier} {confidence}]")

            print(f"🎯 {selection}")

            print(f"🎮 {game}")

            print(f"📚 {book} {odds_display}")

            if reasoning:
                print(f"🧠 {reasoning}")

    print("\n" + "-" * 65)
    if prop_picks:
        print(f"🔥 BEST PLAYER PROP: {prop_picks[0].get('selection')}")
    if game_picks:
        print(f"🔥 BEST GAME BET: {game_picks[0].get('selection')}")
    print("-" * 65)


# ============================================================
# MAIN ANALYZER
# ============================================================

def analyze_nfl(
    scrape_date=None,
):
    if scrape_date is None:
        scrape_date = (
            datetime.now()
            .strftime("%Y-%m-%d")
        )

    print(
        f"\n{'=' * 65}"
    )

    print(
        f"🏈 NFL ANALYZER — "
        f"{scrape_date}"
    )

    print(
        "Markets: Moneyline | "
        "Spread | Game Total | Player Props"
    )

    print(
        "Books: FanDuel | Caesars | PropFinder prop-price source"
    )

    print("NFL player props: ENABLED via PropFinder export")

    print(
        f"{'=' * 65}"
    )

    # --------------------------------------------------------
    # Load odds
    # --------------------------------------------------------

    odds_data = load_nfl_odds(
        scrape_date
    )

    intelligence = load_nfl_intelligence(scrape_date)
    nfl_week = nfl_week_from_intelligence(intelligence)
    prop_candidates = []
    model_index = build_prop_finder_model_index(
        intelligence["games"].get("cards", [])
    )

    print(
        f"📊 PropFinder: "
        f"{len(intelligence['games'].get('cards', []))} projections | "
        f"{len(intelligence['weather'].get('blocks', []))} weather blocks | "
        f"{len(intelligence['home_field'].get('blocks', []))} HFA blocks | "
        f"{sum(len(v.get('rows', [])) for v in intelligence['props'].get('views', {}).values())} props | "
        f"Week {nfl_week}"
    )

    all_games = odds_data.get(
        "games",
        [],
    )

    print(
        f"\n📥 Loaded "
        f"{len(all_games)} NFL games "
        f"from odds file"
    )

    # --------------------------------------------------------
    # Limit to current slate
    # --------------------------------------------------------

    games = filter_nfl_slate(
        all_games,
        scrape_date,
    )

    eligible_prop_teams = teams_in_odds_slate(games)
    model_context = format_prop_finder_context(intelligence, games)
    prop_candidates = build_prop_candidates(
        intelligence["props"],
        eligible_teams=eligible_prop_teams,
        week=nfl_week,
    )

    print(
        f"📅 NFL games on "
        f"{scrape_date}: "
        f"{len(games)} games"
    )
    print(
        f"🎯 Eligible NFL props: {len(prop_candidates)} "
        f"across {len(eligible_prop_teams)} slate teams"
    )

    if not games:
        print(
            f"\n⚠️ No NFL games scheduled for "
            f"{scrape_date}."
        )

        fallback_props = prop_candidates[:MAX_PICKS]
        for rank, pick in enumerate(fallback_props, start=1):
            pick["rank"] = rank

        return save_nfl_picks(
            scrape_date,
            games,
            fallback_props,
            [],
            len(prop_candidates),
        )

    # --------------------------------------------------------
    # Load news
    # --------------------------------------------------------

    news_data = load_news(
        scrape_date,
        "nfl",
    )

    print(
        f"📰 Loaded news for "
        f"{len(news_data)} games"
    )

    # --------------------------------------------------------
    # Claude analysis
    # --------------------------------------------------------

    claude_data = analyze_with_claude(
        games,
        news_data,
        scrape_date,
        model_context,
    )

    claude_picks = claude_data.get(
        "picks",
        [],
    )

    print(
        f"\n🤖 Claude returned "
        f"{len(claude_picks)} "
        f"candidate picks"
    )

    # --------------------------------------------------------
    # Deterministic verification
    # --------------------------------------------------------

    validated, rejected = (
        validate_nfl_picks(
            claude_data,
            games,
            model_index,
        )
    )

    # Keep two independent Top 5 lists. Game picks remain Claude-selected and
    # sportsbook-validated; player props remain export-validated.
    game_picks = sorted(
        validated,
        key=lambda pick: pick.get("prediction_confidence", 0),
        reverse=True,
    )[:MAX_PICKS]
    player_prop_picks = prop_candidates[:MAX_PICKS]

    for rank, pick in enumerate(player_prop_picks, start=1):
        pick["rank"] = rank
    for rank, pick in enumerate(game_picks, start=1):
        pick["rank"] = rank

    # Preserve the legacy combined field for downstream email/main.py code.
    validated = player_prop_picks + game_picks

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    output = save_nfl_picks(
        scrape_date,
        games,
        validated,
        rejected,
        len(prop_candidates),
    )

    # --------------------------------------------------------
    # Print
    # --------------------------------------------------------

    print_nfl_results(
        validated
    )

    return output


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        requested_date = (
            sys.argv[1]
        )
    else:
        requested_date = None

    analyze_nfl(
        requested_date
    )
