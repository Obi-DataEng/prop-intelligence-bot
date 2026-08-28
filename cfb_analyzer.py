import os
import sys
import json
import re
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

CFB_MODEL = os.getenv(
    "CFB_MODEL",
    "claude-sonnet-4-5",
)



MIN_CONFIDENCE = 72
MAX_PICKS = 5

VALID_BOOKS = {
    "FD": "FanDuel",
    "CZS": "Caesars",
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

def load_cfb_odds(scrape_date):
    filepath = (
        f"logs/{scrape_date}_cfb_odds.json"
    )

    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"CFB odds file not found: {filepath}"
        )

    with open(
        filepath,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


# ============================================================
# FILTER CURRENT CFB SLATE
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


def filter_cfb_slate(
    games,
    scrape_date,
):
    """
    Keep ONLY CFB games occurring on scrape_date
    in Eastern Time.

    This keeps CFB aligned with the MLB/NBA/WNBA
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

def format_cfb_odds_for_prompt(games):
    """
    Convert CFB sportsbook data into compact,
    readable prompt text.
    """
    if not games:
        return "No CFB games available."

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

def build_cfb_prompt(
    games,
    news_data,
    scrape_date,
):
    odds_text = format_cfb_odds_for_prompt(
        games
    )

    news_text = format_news_for_prompt(
        news_data,
        "CFB",
    )

    return f"""
You are a disciplined college football betting analyst.

DATE:
{scrape_date}

============================================================
STRICT SCOPE
============================================================

COLLEGE PLAYER PROPS ARE OUT OF SCOPE.

Do not analyze, recommend, rank, mention, or create
college player props.

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

Evaluate the entire supplied CFB slate and identify the
strongest betting opportunities across moneylines,
spreads, and game totals.

Rank all eligible markets together.

Return AT MOST {MAX_PICKS} picks.

You may return fewer than {MAX_PICKS}.

If only 1 or 2 bets genuinely qualify, return only those.

If nothing meets the evidence standard, return zero picks.

NEVER manufacture picks just to reach {MAX_PICKS}.

============================================================
CONFIDENCE
============================================================

Only return bets with confidence >= {MIN_CONFIDENCE}.

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
- returning production
- coaching/system changes
- recent team-specific reporting
- home/road context
- neutral-site context
- meaningful market disagreement between books

News articles may contain generic college football content.

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
CFB ODDS
============================================================

{odds_text}

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
  "league": "CFB",
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
):
    ensure_anthropic_key()

    client = Anthropic(
        api_key=ANTHROPIC_API_KEY
    )

    prompt = build_cfb_prompt(
        games,
        news_data,
        scrape_date,
    )

    print(
        "\n🧠 Sending CFB slate to Claude..."
    )

    print(
        f"   🎮 Games in analysis: "
        f"{len(games)}"
    )

    response = client.messages.create(
        model=CFB_MODEL,
        max_tokens=5000,
        temperature=0.2,
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


# ============================================================
# VALIDATE ALL CLAUDE PICKS
# ============================================================

def validate_cfb_picks(
    claude_data,
    games,
):
    print(
        "\n🔎 Validating Claude CFB picks "
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

def save_cfb_picks(
    scrape_date,
    games,
    validated,
    rejected,
):
    output = {
        "date": scrape_date,
        "league": "CFB",
        "markets": [
            "moneyline",
            "spread",
            "game_total",
        ],
        "player_props_enabled": False,
        "books": [
            "FD",
            "CZS",
        ],
        "games_analyzed": len(games),
        "picks": validated,
        "rejected_picks": rejected,
    }

    os.makedirs(
        "logs",
        exist_ok=True,
    )

    filepath = (
        f"logs/{scrape_date}_"
        f"cfb_picks.json"
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
        f"\n💾 CFB picks saved to "
        f"{filepath}"
    )

    return output


# ============================================================
# DISPLAY
# ============================================================

def print_cfb_results(
    picks,
):
    print(
        "\n"
        + "=" * 65
    )

    print(
        "🏈 CFB VALIDATED PICKS"
    )

    print(
        "=" * 65
    )

    if not picks:
        print(
            "\nNo CFB bets cleared "
            "the validation threshold."
        )

        return

    for pick in picks:
        rank = pick.get(
            "rank",
            "",
        )

        tier = pick.get(
            "confidence_tier",
            "",
        )

        confidence = pick.get(
            "prediction_confidence",
            "",
        )

        selection = pick.get(
            "selection",
            "",
        )

        book = pick.get(
            "best_book",
            "",
        )

        odds = pick.get(
            "best_odds",
            "",
        )

        game = pick.get(
            "game",
            "",
        )

        reasoning = pick.get(
            "reasoning",
            "",
        )

        if isinstance(
            odds,
            (int, float),
        ) and odds > 0:
            odds_display = (
                f"+{odds}"
            )

        else:
            odds_display = str(
                odds
            )

        print(
            f"\n#{rank} "
            f"[{tier} {confidence}]"
        )

        print(
            f"🎯 {selection}"
        )

        print(
            f"🎮 {game}"
        )

        print(
            f"📚 {book} "
            f"{odds_display}"
        )

        if reasoning:
            print(
                f"🧠 {reasoning}"
            )

    best = picks[0]

    print(
        "\n"
        + "-" * 65
    )

    print(
        f"🔥 BEST BET: "
        f"{best.get('selection')} "
        f"("
        f"{best.get('best_book')} "
        f"{'+' if isinstance(best.get('best_odds'), (int, float)) and best.get('best_odds') > 0 else ''}"
        f"{best.get('best_odds')}"
        f")"
    )

    print(
        "-" * 65
    )


# ============================================================
# MAIN ANALYZER
# ============================================================

def analyze_cfb(
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
        f"🏈 CFB ANALYZER — "
        f"{scrape_date}"
    )

    print(
        "Markets: Moneyline | "
        "Spread | Game Total"
    )

    print(
        "Books: FanDuel | Caesars"
    )

    print(
        "College player props: DISABLED"
    )

    print(
        f"{'=' * 65}"
    )

    # --------------------------------------------------------
    # Load odds
    # --------------------------------------------------------

    odds_data = load_cfb_odds(
        scrape_date
    )

    all_games = odds_data.get(
        "games",
        [],
    )

    print(
        f"\n📥 Loaded "
        f"{len(all_games)} CFB games "
        f"from odds file"
    )

    # --------------------------------------------------------
    # Limit to current slate
    # --------------------------------------------------------

    games = filter_cfb_slate(
        all_games,
        scrape_date,
    )

    print(
        f"📅 CFB games on "
        f"{scrape_date}: "
        f"{len(games)} games"
    )

    if not games:
        print(
            f"\n⚠️ No CFB games scheduled for "
            f"{scrape_date}."
        )

        return save_cfb_picks(
            scrape_date,
            games,
            [],
            [],
        )

    # --------------------------------------------------------
    # Load news
    # --------------------------------------------------------

    news_data = load_news(
        scrape_date,
        "cfb",
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
        validate_cfb_picks(
            claude_data,
            games,
        )
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    output = save_cfb_picks(
        scrape_date,
        games,
        validated,
        rejected,
    )

    # --------------------------------------------------------
    # Print
    # --------------------------------------------------------

    print_cfb_results(
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

    analyze_cfb(
        requested_date
    )