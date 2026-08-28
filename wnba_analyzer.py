import anthropic
import json
import os
import re
from datetime import datetime

from dotenv import load_dotenv
from news_fetcher import load_news, format_news_for_prompt

load_dotenv()


WNBA_SOURCE_FILES = [
    "wnba_research",
    "wnba_player_stats",
    "wnba_team_stats",
    "wnba_hit_rate",
    "wnba_injury_reports",
    "wnba_volume_trends",
    "wnba_injury_splits",
    "wnba_odds_discrepancies",
]


def load_wnba_data(scrape_date):
    data = {}

    for name in WNBA_SOURCE_FILES:
        filepath = f"logs/{scrape_date}_{name}.json"

        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                data[name] = json.load(f)

            print(f"   📂 Loaded {name}")
        else:
            print(f"   ⚠️ Missing {name}")
            data[name] = {}

    return data


def load_wnba_odds(scrape_date):
    """
    Load external sportsbook odds if odds_fetcher.py has produced a WNBA
    odds file. PropFinder Odds Discrepancies is loaded separately as one
    of the WNBA research sources.
    """
    filepath = f"logs/{scrape_date}_wnba_odds.json"

    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    print("   ⚠️ No external WNBA odds file found")
    return {}


def format_wnba_odds_for_prompt(odds_data):
    if not odds_data:
        return "No external sportsbook odds data available"

    text = ""
    games = odds_data.get("games", [])
    player_props = odds_data.get("player_props", {})

    market_labels = {
        "player_points": "PTS",
        "player_rebounds": "REB",
        "player_assists": "AST",
        "player_threes": "3PM",
        "player_points_rebounds_assists": "PRA",
        "player_points_rebounds": "PR",
        "player_points_assists": "PA",
        "player_rebounds_assists": "RA",
        "player_steals": "STL",
        "player_blocks": "BLK",
    }

    for game in games:
        home = game.get("home_team", "")
        away = game.get("away_team", "")

        if not home or not away:
            continue

        game_key = f"{away}@{home}"
        books = game.get("bookmakers", {})

        text += f"\n{away} @ {home}\n"

        for book, book_data in books.items():
            text += (
                f"  {book}: "
                f"ML {book_data.get('away_ml', 'N/A')}/"
                f"{book_data.get('home_ml', 'N/A')} | "
                f"Spread {book_data.get('away_spread', 'N/A')} | "
                f"O/U {book_data.get('total', 'N/A')}\n"
            )

        props = player_props.get(game_key, {})

        if props:
            text += "  PLAYER PROPS:\n"

            for market, players in props.items():
                label = market_labels.get(market, market)
                text += f"    {label}:\n"

                for player, prop_data in list(players.items())[:12]:
                    line = prop_data.get("line", "N/A")

                    book_parts = []

                    for book_name, book_values in prop_data.items():
                        if book_name == "line":
                            continue

                        if not isinstance(book_values, dict):
                            continue

                        over = book_values.get("over")
                        under = book_values.get("under")

                        if over is not None or under is not None:
                            book_parts.append(
                                f"{book_name}:O{over}/U{under}"
                            )

                    text += (
                        f"      {player} {line} | "
                        + " ".join(book_parts[:6])
                        + "\n"
                    )

    return text[:10000]


def rows_to_text(rows, max_rows=120, max_chars=9000):
    if not rows:
        return ""

    output = []

    for row in rows[:max_rows]:
        if isinstance(row, list):
            output.append(" | ".join(str(v) for v in row))
        else:
            output.append(str(row))

    return "\n".join(output)[:max_chars]


def structured_source_text(source, max_rows=120, max_chars=9000):
    if not isinstance(source, dict):
        return ""

    headers = source.get("headers", [])
    grid_rows = source.get("grid_rows", [])
    html_rows = source.get("html_rows", [])

    rows = grid_rows if grid_rows else html_rows

    pieces = []

    if headers:
        pieces.append(
            "HEADERS: "
            + " | ".join(str(v) for v in headers)
        )

    if rows:
        pieces.append(
            rows_to_text(
                rows,
                max_rows=max_rows,
                max_chars=max_chars,
            )
        )
    else:
        full_text = source.get("fullText", "")

        if full_text:
            pieces.append(full_text[:max_chars])

    return "\n".join(pieces)[:max_chars]


def research_text(data):
    source = data.get("wnba_research", {})

    if not isinstance(source, dict):
        return ""

    headers = source.get("headers", [])
    rows = source.get("rows", [])

    pieces = []

    if headers:
        pieces.append(
            "HEADERS: "
            + " | ".join(str(v) for v in headers)
        )

    pieces.append(
        rows_to_text(
            rows,
            max_rows=327,
            max_chars=18000,
        )
    )

    return "\n".join(pieces)[:18000]


def volume_trends_text(data):
    source = data.get("wnba_volume_trends", {})

    if not isinstance(source, dict):
        return ""

    windows = source.get("windows", {})
    sections = []

    # L10 is intentionally first and receives the largest prompt budget.
    budgets = {
        "L10": 7000,
        "L5": 3500,
        "L3": 2500,
        "L15": 3000,
    }

    for window in ["L10", "L5", "L3", "L15"]:
        window_data = windows.get(window, {})

        if not window_data:
            continue

        section = structured_source_text(
            window_data,
            max_rows=80,
            max_chars=budgets[window],
        )

        if section:
            sections.append(
                f"=== {window} ===\n{section}"
            )

    return "\n\n".join(sections)[:16000]


def odds_discrepancy_text(data):
    source = data.get("wnba_odds_discrepancies", {})

    if not isinstance(source, dict):
        return ""

    return structured_source_text(
        source,
        max_rows=110,
        max_chars=10000,
    )


def safe_load_news(scrape_date):
    try:
        news_data = load_news(
            scrape_date,
            sport="wnba",
        )
        return format_news_for_prompt(news_data)
    except Exception as e:
        print(f"   ⚠️ WNBA news unavailable: {e}")
        return "No WNBA news data available"


def build_wnba_prompt(
    data,
    odds_text,
    scrape_date,
    odds_data=None,
):
    if odds_data is None:
        odds_data = {}

    research = research_text(data)

    player_stats = structured_source_text(
        data.get("wnba_player_stats", {}),
        max_rows=60,
        max_chars=7000,
    )

    team_stats = structured_source_text(
        data.get("wnba_team_stats", {}),
        max_rows=25,
        max_chars=5000,
    )

    hit_rate = structured_source_text(
        data.get("wnba_hit_rate", {}),
        max_rows=80,
        max_chars=8000,
    )

    injuries = structured_source_text(
        data.get("wnba_injury_reports", {}),
        max_rows=50,
        max_chars=5000,
    )

    volume = volume_trends_text(data)

    injury_splits = structured_source_text(
        data.get("wnba_injury_splits", {}),
        max_rows=60,
        max_chars=7000,
    )

    discrepancies = odds_discrepancy_text(data)

    news_text = safe_load_news(scrape_date)

    games_today = [
        f"{g.get('away_team')} @ {g.get('home_team')}"
        for g in odds_data.get("games", [])
        if g.get("away_team") and g.get("home_team")
    ]

    games_today_str = (
        "\n".join(f"  - {game}" for game in games_today)
        if games_today
        else (
            "  External WNBA odds did not provide a game list. "
            "Use only clearly current-day games/props supported by the "
            "PropFinder Research data; do not invent games."
        )
    )

    prompt = f"""
You are an expert WNBA betting analyst evaluating the complete betting slate,
including player props, moneylines, spreads, and game totals. 
Today is {scrape_date}.

Your objective is NOT to force bets. Return up to the 5 strongest qualified WNBA bets across ALL supported markets.

DATE: {scrape_date}

=== TODAY'S GAMES FROM EXTERNAL ODDS ===
{games_today_str}

=== WNBA RESEARCH ===
This is the primary candidate/prop source. Use the actual headers supplied
by the scraper rather than assuming a column order.
{research}

=== PLAYER STATS / SEASON BASELINE ===
{player_stats}

=== VOLUME TRENDS ===
L10 IS THE PRIMARY RECENT-FORM WINDOW.
L3 and L5 are short-term acceleration signals.
L15 and season data help determine whether the change is persistent.
Prefer trends supported by opportunity metrics such as minutes, usage,
FGA/3PA, rebound chances, potential assists and passes instead of relying
on shooting efficiency alone.
{volume}

=== INJURY SPLITS ===
Use this to identify role, minutes, usage and opportunity changes when
teammates are absent. SAMPLE SIZE MATTERS. A one-game split is weak
evidence and must never be treated like a stable multi-game role change.
{injury_splits}

=== CURRENT INJURY REPORTS ===
{injuries}

=== HIT RATE MATRIX ===
Use hit rates as confirmation, not as the sole reason for a pick.
{hit_rate}

=== TEAM STATS ===
{team_stats}

=== PROPFINDER ODDS DISCREPANCIES ===
This section measures MARKET PRICING DIFFERENCES. It does NOT measure the
probability that a prop will hit.
{discrepancies}

=== EXTERNAL SPORTSBOOK ODDS ===
{odds_text}

=== RECENT WNBA NEWS ===
{news_text}

ANALYSIS FRAMEWORK

Keep two concepts separate:

1. PREDICTION CONFIDENCE
   Determine whether the prop itself is likely to win.

   Weight the evidence conceptually in this order:
   - WNBA Research / actual prop line
   - L10 Volume Trends
   - Player season baseline
   - Injury Splits when the relevant teammate absence applies
   - Hit Rate Matrix
   - Current Injury Reports
   - Team context
   - L5/L3 acceleration and L15 persistence

2. MARKET VALUE
   Determine whether the available price is attractive.

   Use:
   - external sportsbook odds
   - PropFinder Odds Discrepancies

   A large discrepancy alone is NEVER evidence that a bet is likely to win.

HARD SAFETY RULE FOR LONGSHOTS

If a discrepancy row shows something like:
- 0/37 hit rate
- 0/38 hit rate
- 1/35 hit rate
- extremely high plus-money pricing

do NOT recommend it merely because one sportsbook offers a much larger
price than another.

A prop with a huge market discrepancy and terrible historical probability
should normally be a PASS.

INJURY-SPLIT RELIABILITY

Treat injury split samples approximately as:
- 1 game: very low reliability
- 2-3 games: low reliability
- 4-7 games: moderate supporting evidence
- 8+ games: materially useful evidence

Never let a tiny injury-split sample override stronger season/L10 evidence.

WHAT MAKES A STRONG WNBA PICK

Prefer:
- actual current prop line clearly present in the data
- strong L10 performance relative to the line
- recent opportunity increase supporting the production
- season baseline reasonably compatible with the line
- strong hit-rate confirmation
- applicable injury-driven role increase with a meaningful sample
- player not listed Out
- multiple independent signals agreeing
- fair or positive sportsbook pricing

Downgrade:
- production driven only by a temporary FG%/3P% spike
- low-minute players
- tiny injury-split samples
- conflicting L10 vs season/opportunity data
- questionable injury status
- props with terrible historical hit rates
- huge plus-money longshots
- market discrepancy without basketball evidence

SELECTION RULES

1. Evaluate ALL supported WNBA betting markets together:
   - Player props
   - Moneylines
   - Spreads
   - Game totals (Over/Under)

2. Rank every qualified betting opportunity against every other opportunity,
   regardless of market type. Do NOT reserve slots for any category.

3. Return up to 5 of the strongest bets on the entire slate.
   It is acceptable to return fewer than 5 when fewer than 5 bets meet the
   confidence and evidence requirements.

4. A player prop should beat a game market only when its evidence is stronger.
   A moneyline, spread, or game total should beat a player prop when its
   evidence is stronger.

5. Because the supplied research data is richer for player-level analysis,
   hold game markets to a higher evidence standard.

6. Never manufacture a pick to reach 5 bets.
7. Ignore players listed Out.
8. Never invent a line, sportsbook, price, opponent, hit rate or statistic.
9. If external odds are available, the selected line must exist there.
10. Do not use Odds Discrepancies as prediction confidence.
11. Rank picks by prediction confidence first, then market value.
12. Confidence scores must reflect evidence quality; do not inflate scores
    merely to fill the output.
13. Do not use Odds Discrepancies as prediction confidence.
14. Rank picks by prediction confidence first, then market value.
15. Confidence scores must reflect evidence quality; do not inflate scores
    merely to fill the output.

CONFIDENCE GUIDANCE

Elite: 88-95
High: 80-87
Medium: 72-79

Do not output a pick below 72 confidence.

MARKET VALUE GUIDANCE

Strong:
- favorable price plus strong prediction evidence

Positive:
- some meaningful price advantage with good prediction evidence

Neutral:
- fair price / little shopping advantage

Negative:
- unattractive price even if the basketball case is reasonable

REQUIRED OUTPUT FORMAT

Return ONLY valid JSON. No markdown fences and no prose outside JSON.

{{
  "top_picks": [
    {{
  "rank": 1,
  "pick_type": "player_prop | moneyline | spread | game_total",
  "category": "Points | Rebounds | Assists | Three Pointers | PRA | PR | PA | RA | Steals | Blocks | Moneyline | Spread | Game Total",
  "selection": "Human-readable exact wager",
  "player_name": "Player Name or null",
  "team": "TEAM",
  "opponent": "OPP",
  "game": "AWAY @ HOME",
  "prop_line": 18.5,
  "game_line": null,
  "over_under": "OVER | UNDER | null",
  "best_book": "FD | MGM | CZS | ESPN | null",
  "best_odds": -115,
  "prediction_confidence": 86,
  "confidence_tier": "High",
  "market_value_score": 74,
  "market_value_tier": "Strong | Positive | Neutral | Negative",
  "season_avg": 20.1,
  "l3_avg": 22.0,
  "l5_avg": 21.4,
  "l10_avg": 20.9,
  "l15_avg": 20.3,
  "hit_rate_season": "68%",
  "hit_rate_l10": "70%",
  "injury_split_games": 8,
  "injury_split_note": "Role increases without Player X, or null",
  "opportunity_signals": [],
  "key_factors": [],
  "risk_factors": [],
  "reasoning": "2-4 concise sentences.",
  "line_shop_note": null
}}
  ],
  "passes": [
    {{
      "player_name": "Player Name",
      "prop": "OVER 12.5 Rebounds",
      "reason": "Large odds discrepancy but 0/37 season hit rate."
    }}
  ],
  "slate_summary": "Brief assessment of the WNBA slate and evidence quality.",
  "best_bet": "Single best WNBA bet in one sentence, or No qualifying bet."
}}

Return ONLY valid JSON.
"""

    return prompt


def parse_json_response(response_text):
    clean = response_text.strip()

    if clean.startswith("```"):
        clean = clean.split("```", 1)[1]

        if clean.startswith("json"):
            clean = clean[4:]

        if "```" in clean:
            clean = clean.split("```", 1)[0]

    return json.loads(clean.strip())


def run_wnba_analyzer(scrape_date=None, odds_data=None):
    if not scrape_date:
        scrape_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'=' * 50}")
    print(f"🏀 WNBA Analyzer — {scrape_date}")
    print(f"{'=' * 50}\n")

    data = load_wnba_data(scrape_date)

    if not odds_data:
        odds_data = load_wnba_odds(scrape_date)

        print(
            f"   📂 Loaded wnba_odds "
            f"({len(odds_data.get('games', []))} games)"
        )

    odds_text = format_wnba_odds_for_prompt(odds_data)

    prompt = build_wnba_prompt(
        data,
        odds_text,
        scrape_date,
        odds_data,
    )

    print("\n🤖 Claude Haiku analyzing WNBA slate...")

    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Missing ANTHROPIC_API_KEY in .env"
        )

    client = anthropic.Anthropic(
        api_key=api_key
    )

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=5000,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    response_text = message.content[0].text

    print(
        f"✅ Claude responded "
        f"({len(response_text)} chars)"
    )

    print(
        f"💰 Tokens: "
        f"{message.usage.input_tokens} in / "
        f"{message.usage.output_tokens} out"
    )

    try:
        picks_data = parse_json_response(
            response_text
        )

        print("✅ JSON parsed successfully")

        print("\n🔎 Validating Claude picks against external odds...")

        picks_data = validate_and_correct_picks(
            picks_data,
            odds_data,
            )

        validation = picks_data.get("validation", {})

        print(
            f"   ✅ {validation.get('validated_count', 0)} validated | "
            f"❌ {validation.get('rejected_count', 0)} rejected"
        )

    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        print(
            f"Raw response: "
            f"{response_text[:1000]}"
        )
        return None

    top_picks = picks_data.get(
        "top_picks",
        [],
    )

    best_bet = picks_data.get(
        "best_bet",
        "No qualifying bet.",
    )

    print(f"\n🎯 BEST BET: {best_bet}")

    print(
        f"📋 "
        f"{picks_data.get('slate_summary', '')}"
    )

    print(f"\n{'=' * 50}")
    print(
        f"⭐ TODAY'S TOP WNBA PICKS "
        f"({len(top_picks)} picks)"
    )
    print(f"{'=' * 50}")

    if not top_picks:
        print(
            "\n  No WNBA props met the "
            "minimum confidence threshold."
        )

    for pick in top_picks:
        tier = pick.get(
            "confidence_tier",
            "Medium",
        )

        player = pick.get(
            "player_name",
            "N/A",
        )

        category = pick.get(
            "category",
            "",
        )

        over_under = pick.get(
            "over_under",
            "",
        )

        line = pick.get(
            "prop_line",
            "",
        )

        book = pick.get(
            "best_book",
        )

        odds = pick.get(
            "best_odds",
        )

        prediction = pick.get(
            "prediction_confidence",
            "",
        )

        market_tier = pick.get(
            "market_value_tier",
            "",
        )

        l10 = pick.get(
            "l10_avg",
            "",
        )

        season = pick.get(
            "season_avg",
            "",
        )

        hit_l10 = pick.get(
            "hit_rate_l10",
            "",
        )

        print(
            f"\n  #{pick.get('rank')} "
            f"[{tier} {prediction}] "
            f"{player} — {category} | "
            f"{over_under} {line}"
        )

        print(
            f"     📅 {pick.get('game')} | "
            f"{pick.get('team')} vs "
            f"{pick.get('opponent')}"
        )

        print(
            f"     📈 Season: {season} | "
            f"L10: {l10} | "
            f"L10 Hit: {hit_l10}"
        )

        print(
            f"     💵 {book} {odds} | "
            f"Market Value: {market_tier}"
        )

        print(
            f"     📝 "
            f"{pick.get('reasoning', '')[:220]}"
        )

    passes = picks_data.get(
        "passes",
        [],
    )

    if passes:
        print(f"\n{'=' * 50}")
        print("🚫 NOTABLE PASSES")
        print(f"{'=' * 50}")

        for item in passes:
            if item.get("bet"):
                print(
                    f"  • {item.get('bet')}: "
                    f"{item.get('reason', '')}"
                )
            else:
                print(
                    f"  • {item.get('player_name', '')} "
                    f"{item.get('prop', '')}: "
                    f"{item.get('reason', '')}"
                )

    print(
        f"\n📊 Total WNBA picks: "
        f"{len(top_picks)}"
    )

    output_file = (
        f"logs/{scrape_date}_wnba_picks.json"
    )

    with open(
        output_file,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            picks_data,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"✅ WNBA picks saved to "
        f"{output_file}"
    )

    return picks_data

# ============================================================
# DETERMINISTIC ODDS + PICK VALIDATION
# ============================================================

def normalize_text(value):
    """Normalize text for safer comparisons."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def numbers_equal(a, b, tolerance=0.001):
    """Compare numeric values safely."""
    try:
        return abs(float(a) - float(b)) <= tolerance
    except (TypeError, ValueError):
        return False


def confidence_tier(score):
    """
    Deterministically assign confidence tier.

    Elite: 88+
    High: 80-87
    Medium: 72-79
    Below Threshold: <72
    """
    try:
        score = float(score)
    except (TypeError, ValueError):
        return "Below Threshold"

    if score >= 88:
        return "Elite"
    if score >= 80:
        return "High"
    if score >= 72:
        return "Medium"
    return "Below Threshold"


def best_american_price(offers):
    """
    Return the best American odds among identical wagers.

    With American odds, the numerically largest price is best:
      -105 is better than -110
      +120 is better than +105
      +100 is better than -105

    offers format:
    [
        {"book": "FD", "odds": -108},
        {"book": "MGM", "odds": -115},
        ...
    ]
    """
    valid = []

    for offer in offers:
        try:
            odds = int(offer.get("odds"))
            valid.append({
                "book": offer.get("book"),
                "odds": odds,
            })
        except (TypeError, ValueError):
            continue

    if not valid:
        return None

    return max(valid, key=lambda x: x["odds"])


def player_market_key(category):
    """Map Claude category names to The Odds API market keys."""
    category = normalize_text(category)

    mapping = {
        "points": "player_points",
        "point": "player_points",

        "rebounds": "player_rebounds",
        "rebound": "player_rebounds",

        "assists": "player_assists",
        "assist": "player_assists",

        "three pointers": "player_threes",
        "three pointer": "player_threes",
        "3 pointers": "player_threes",
        "3 pointer": "player_threes",
        "3pm": "player_threes",
        "threes": "player_threes",

        "points + rebounds + assists":
            "player_points_rebounds_assists",
        "points+rebounds+assists":
            "player_points_rebounds_assists",
        "pra":
            "player_points_rebounds_assists",

        "points + rebounds":
            "player_points_rebounds",
        "points+rebounds":
            "player_points_rebounds",
        "pr":
            "player_points_rebounds",

        "points + assists":
            "player_points_assists",
        "points+assists":
            "player_points_assists",
        "pa":
            "player_points_assists",

        "rebounds + assists":
            "player_rebounds_assists",
        "rebounds+assists":
            "player_rebounds_assists",
        "ra":
            "player_rebounds_assists",

        "steals": "player_steals",
        "steal": "player_steals",

        "blocks": "player_blocks",
        "block": "player_blocks",
    }

    return mapping.get(category)


def find_odds_game(pick, odds_data):
    """
    Find the external odds game corresponding to Claude's pick.
    """
    games = odds_data.get("games", [])

    pick_game = normalize_text(pick.get("game"))
    pick_team = normalize_text(pick.get("team"))
    pick_opponent = normalize_text(pick.get("opponent"))

    # First try exact matchup text.
    for game in games:
        away = game.get("away_team", "")
        home = game.get("home_team", "")

        matchup_variants = [
            f"{away} @ {home}",
            f"{away}@{home}",
            f"{away} at {home}",
        ]

        if pick_game:
            for matchup in matchup_variants:
                if normalize_text(matchup) == pick_game:
                    return game

    # Then try team/opponent containment.
    for game in games:
        away = normalize_text(game.get("away_team"))
        home = normalize_text(game.get("home_team"))

        if (
            pick_team
            and pick_opponent
            and (
                (pick_team in away and pick_opponent in home)
                or
                (pick_team in home and pick_opponent in away)
                or
                (away in pick_team and home in pick_opponent)
                or
                (home in pick_team and away in pick_opponent)
            )
        ):
            return game

    return None


def find_selected_team_side(pick, game):
    """
    Determine whether the pick refers to the home or away team.
    """
    selection = normalize_text(pick.get("selection"))
    team = normalize_text(pick.get("team"))

    home = normalize_text(game.get("home_team"))
    away = normalize_text(game.get("away_team"))

    if home and (home in selection or home in team):
        return "home"

    if away and (away in selection or away in team):
        return "away"

    # Last fallback: compare meaningful team-name pieces.
    home_parts = [p for p in home.split() if len(p) > 3]
    away_parts = [p for p in away.split() if len(p) > 3]

    if any(part in selection or part in team for part in home_parts):
        return "home"

    if any(part in selection or part in team for part in away_parts):
        return "away"

    return None


def validate_player_prop_pick(pick, odds_data):
    """
    Verify a player prop exists in external odds and select
    the best sportsbook price for the EXACT SAME line and side.
    """
    props = odds_data.get("player_props", {})

    category = pick.get("category")
    market_key = player_market_key(category)

    if not market_key:
        return None, f"Unsupported player prop category: {category}"

    player = normalize_text(pick.get("player_name"))

    if not player:
        # Backward compatibility with older Claude output.
        player = normalize_text(pick.get("player"))

    if not player:
        return None, "Missing player name"

    try:
        selected_line = float(pick.get("prop_line"))
    except (TypeError, ValueError):
        try:
            selected_line = float(pick.get("line"))
        except (TypeError, ValueError):
            return None, "Missing or invalid player prop line"

    side = normalize_text(pick.get("over_under"))

    if side not in ("over", "under"):
        selection = normalize_text(pick.get("selection"))

        if "over" in selection:
            side = "over"
        elif "under" in selection:
            side = "under"
        else:
            return None, "Missing OVER/UNDER side"

    matched_player_data = None
    matched_game_key = None

    # Locate the player/market across all games.
    for game_key, game_markets in props.items():
        market = game_markets.get(market_key, {})

        for player_name, player_data in market.items():
            if normalize_text(player_name) == player:
                matched_player_data = player_data
                matched_game_key = game_key
                break

        if matched_player_data:
            break

    if not matched_player_data:
        return None, (
            f"No external odds found for "
            f"{pick.get('player_name') or pick.get('player')} "
            f"{category}"
        )

    offers = []

    # New odds-fetcher format:
    # player_data = {
    #   "line": 25.5,
    #   "FD": {"line": 25.5, "over": -108, "under": -112},
    #   ...
    # }
    for book, book_data in matched_player_data.items():

        if book == "line":
            continue

        if not isinstance(book_data, dict):
            continue

        book_line = book_data.get(
            "line",
            matched_player_data.get("line")
        )

        if not numbers_equal(book_line, selected_line):
            continue

        price = book_data.get(side)

        if price is None:
            continue

        offers.append({
            "book": book,
            "odds": price,
        })

    best = best_american_price(offers)

    if not best:
        return None, (
            f"Exact external line not found: "
            f"{pick.get('player_name') or pick.get('player')} "
            f"{side.upper()} {selected_line} {category}"
        )

    corrected = dict(pick)

    corrected["pick_type"] = "player_prop"
    corrected["prop_line"] = selected_line
    corrected["over_under"] = side.upper()
    corrected["best_book"] = best["book"]
    corrected["best_odds"] = best["odds"]
    corrected["validated_game_key"] = matched_game_key
    corrected["odds_validated"] = True

    corrected["line_shop_note"] = (
        f"{best['book']} {best['odds']:+d} is the best "
        f"available price found for the exact "
        f"{side.upper()} {selected_line} line."
    )

    return corrected, None


def validate_game_pick(pick, odds_data):
    """
    Validate moneyline, spread, or game-total picks against
    external sportsbook odds.
    """
    game = find_odds_game(pick, odds_data)

    if not game:
        return None, f"Could not match external game: {pick.get('game')}"

    pick_type = normalize_text(pick.get("pick_type"))
    bookmakers = game.get("bookmakers", {})

    offers = []

    # --------------------------------------------------------
    # MONEYLINE
    # --------------------------------------------------------
    if pick_type == "moneyline":

        team_side = find_selected_team_side(pick, game)

        if team_side not in ("home", "away"):
            return None, "Could not determine moneyline team"

        odds_field = f"{team_side}_ml"

        for book, book_data in bookmakers.items():
            price = book_data.get(odds_field)

            if price is not None:
                offers.append({
                    "book": book,
                    "odds": price,
                })

        best = best_american_price(offers)

        if not best:
            return None, "No external moneyline price found"

        corrected = dict(pick)
        corrected["best_book"] = best["book"]
        corrected["best_odds"] = best["odds"]
        corrected["odds_validated"] = True

        selected_team = (
            game.get("home_team")
            if team_side == "home"
            else game.get("away_team")
        )

        corrected["selection"] = f"{selected_team} Moneyline"

        corrected["line_shop_note"] = (
            f"{best['book']} {best['odds']:+d} is the best "
            f"available moneyline price found."
        )

        return corrected, None

    # --------------------------------------------------------
    # SPREAD
    # --------------------------------------------------------
    if pick_type == "spread":

        team_side = find_selected_team_side(pick, game)

        if team_side not in ("home", "away"):
            return None, "Could not determine spread team"

        try:
            selected_line = float(
                pick.get("game_line", pick.get("line"))
            )
        except (TypeError, ValueError):
            return None, "Missing spread line"

        line_field = f"{team_side}_spread"
        odds_field = f"{team_side}_spread_odds"

        for book, book_data in bookmakers.items():

            book_line = book_data.get(line_field)

            if not numbers_equal(book_line, selected_line):
                continue

            price = book_data.get(odds_field)

            if price is not None:
                offers.append({
                    "book": book,
                    "odds": price,
                })

        best = best_american_price(offers)

        if not best:
            return None, (
                f"Exact spread {selected_line:+g} "
                f"not found externally"
            )

        corrected = dict(pick)

        corrected["game_line"] = selected_line
        corrected["best_book"] = best["book"]
        corrected["best_odds"] = best["odds"]
        corrected["odds_validated"] = True

        selected_team = (
            game.get("home_team")
            if team_side == "home"
            else game.get("away_team")
        )

        corrected["selection"] = (
            f"{selected_team} {selected_line:+g}"
        )

        corrected["line_shop_note"] = (
            f"{best['book']} {best['odds']:+d} is the best "
            f"available price found for the exact "
            f"{selected_line:+g} spread."
        )

        return corrected, None

    # --------------------------------------------------------
    # GAME TOTAL
    # --------------------------------------------------------
    if pick_type in ("game_total", "total"):

        try:
            selected_line = float(
                pick.get("game_line", pick.get("line"))
            )
        except (TypeError, ValueError):
            return None, "Missing game total line"

        side = normalize_text(pick.get("over_under"))

        if side not in ("over", "under"):
            selection = normalize_text(pick.get("selection"))

            if "over" in selection:
                side = "over"
            elif "under" in selection:
                side = "under"
            else:
                return None, "Missing game-total OVER/UNDER side"

        odds_field = (
            "over_odds"
            if side == "over"
            else "under_odds"
        )

        for book, book_data in bookmakers.items():

            book_total = book_data.get("total")

            if not numbers_equal(book_total, selected_line):
                continue

            price = book_data.get(odds_field)

            if price is not None:
                offers.append({
                    "book": book,
                    "odds": price,
                })

        best = best_american_price(offers)

        if not best:
            return None, (
                f"Exact total {side.upper()} "
                f"{selected_line:g} not found externally"
            )

        corrected = dict(pick)

        corrected["pick_type"] = "game_total"
        corrected["game_line"] = selected_line
        corrected["over_under"] = side.upper()
        corrected["best_book"] = best["book"]
        corrected["best_odds"] = best["odds"]
        corrected["odds_validated"] = True

        corrected["selection"] = (
            f"{side.upper()} {selected_line:g}"
        )

        corrected["line_shop_note"] = (
            f"{best['book']} {best['odds']:+d} is the best "
            f"available price found for the exact "
            f"{side.upper()} {selected_line:g} total."
        )

        return corrected, None

    return None, f"Unsupported game pick type: {pick_type}"


def validate_and_correct_picks(picks_data, odds_data):
    """
    Final deterministic validation layer.

    Claude identifies betting opportunities.
    Python verifies:
      1. confidence tier
      2. minimum confidence
      3. actual sportsbook line
      4. actual sportsbook price
      5. best price for identical wager

    Invalid picks are rejected instead of being silently accepted.
    """

    raw_picks = picks_data.get("top_picks", [])

    validated = []
    rejected = []

    for pick in raw_picks:

        corrected = dict(pick)

        # ----------------------------------------------------
        # CONFIDENCE SCORE
        # ----------------------------------------------------
        try:
            score = int(
                float(
                    corrected.get(
                        "prediction_confidence",
                        corrected.get("confidence_score", 0)
                    )
                )
            )
        except (TypeError, ValueError):
            score = 0

        corrected["prediction_confidence"] = score
        corrected["confidence_score"] = score
        corrected["confidence_tier"] = confidence_tier(score)

        if score < 72:
            rejected.append({
                "pick": corrected,
                "reason": (
                    f"Confidence {score} is below "
                    f"minimum threshold of 72"
                ),
            })
            continue

        # ----------------------------------------------------
        # PICK TYPE
        # ----------------------------------------------------
        pick_type = normalize_text(
            corrected.get("pick_type", "player_prop")
        )

        # Backward compatibility.
        if pick_type in ("player", "prop", "player prop"):
            pick_type = "player_prop"

        corrected["pick_type"] = pick_type

        # ----------------------------------------------------
        # EXTERNAL ODDS VALIDATION
        # ----------------------------------------------------
        if pick_type == "player_prop":

            checked, error = validate_player_prop_pick(
                corrected,
                odds_data
            )

        elif pick_type in (
            "moneyline",
            "spread",
            "game_total",
            "total",
        ):

            checked, error = validate_game_pick(
                corrected,
                odds_data
            )

        else:
            checked = None
            error = f"Unknown pick type: {pick_type}"

        if checked is None:
            rejected.append({
                "pick": corrected,
                "reason": error,
            })
            continue

        validated.append(checked)

    # Keep Claude's original ranking order, but only surviving bets.
    for index, pick in enumerate(validated, start=1):
        pick["rank"] = index

    # Maximum 5.
    validated = validated[:5]

    # --------------------------------------------------------
    # REBUILD BEST BET
    # --------------------------------------------------------
    if validated:
        best = validated[0]

        selection = best.get("selection")

        if not selection:
            if best.get("pick_type") == "player_prop":
                selection = (
                    f"{best.get('player_name', '')} "
                    f"{best.get('over_under', '')} "
                    f"{best.get('prop_line', '')} "
                    f"{best.get('category', '')}"
                ).strip()
            else:
                selection = best.get("category", "Best Bet")

        picks_data["best_bet"] = (
            f"{selection} "
            f"({best.get('best_book')} "
            f"{best.get('best_odds'):+d})"
        )

    else:
        picks_data["best_bet"] = (
            "No bets passed deterministic validation."
        )

    picks_data["top_picks"] = validated
    picks_data["picks"] = validated

    # Add rejected picks to passes so we preserve WHY they failed.
    passes = picks_data.get("passes", [])

    for rejection in rejected:
        rejected_pick = rejection.get("pick", {})

        label = (
            rejected_pick.get("selection")
            or rejected_pick.get("player_name")
            or rejected_pick.get("player")
            or rejected_pick.get("game")
            or "Candidate bet"
        )

        passes.append({
            "bet": label,
            "reason": (
                f"Deterministic validation rejection: "
                f"{rejection.get('reason')}"
            ),
        })

    picks_data["passes"] = passes

    picks_data["validation"] = {
        "enabled": True,
        "validated_count": len(validated),
        "rejected_count": len(rejected),
        "minimum_confidence": 72,
        "confidence_tiers": {
            "Elite": "88-100",
            "High": "80-87",
            "Medium": "72-79",
            "Below Threshold": "0-71",
        },
        "rule": (
            "All recommended bets must match an exact external "
            "sportsbook line. Best American odds are selected "
            "deterministically for identical wagers."
        ),
    }

    return picks_data

if __name__ == "__main__":
    run_wnba_analyzer()
