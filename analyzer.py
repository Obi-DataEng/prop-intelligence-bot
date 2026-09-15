import anthropic
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from news_fetcher import load_news, format_news_for_prompt

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MLB_TEAM_ABBREVIATIONS = {
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL", "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC", "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL", "Detroit Tigers": "DET",
    "Houston Astros": "HOU", "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA", "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN", "New York Mets": "NYM",
    "New York Yankees": "NYY", "Oakland Athletics": "ATH",
    "Athletics": "ATH", "Sacramento Athletics": "ATH",
    "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD", "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB", "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR", "Washington Nationals": "WSH",
}

def load_odds(scrape_date):
    filepath = f"logs/{scrape_date}_odds.json"
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            data = json.load(f)
        print(f"✅ Odds loaded: {len(data.get('games', []))} games, {len(data.get('player_props', {}))} games with props")
        return data
    else:
        print(f"⚠️  No odds file found at {filepath}")
        return None

def format_odds_for_prompt(odds_data):
    if not odds_data:
        return "No odds data available."
    lines = []
    lines.append("== GAME ODDS (FD=FanDuel, MGM=BetMGM, CZS=Caesars, SCR=theScore) ==")
    for game in odds_data.get('games', []):
        away = game['away_team']
        home = game['home_team']
        lines.append(f"\n{away} @ {home}")
        for book, odds in game.get('odds_by_book', {}).items():
            lines.append(f"  {book}: ML {odds['ml_away']}/{odds['ml_home']} | RL {odds['spread_away']}({odds['spread_away_odds']}) | O/U {odds['total_line']} O:{odds['over_odds']} U:{odds['under_odds']}")

    lines.append("\n== PLAYER PROPS BY GAME ==")
    for matchup, props in odds_data.get('player_props', {}).items():
        lines.append(f"\n{matchup}:")
        for prop_key, prop_label in [('hr','HR'),('hits','Hits'),('total_bases','Total Bases'),('pitcher_k','Pitcher Ks'),('batter_k','Batter Ks')]:
            if props.get(prop_key):
                lines.append(f"  {prop_label}:")
                seen = set()
                for prop in props[prop_key]:
                    key = f"{prop['player']}-{prop['pick']}"
                    if key not in seen:
                        seen.add(key)
                        book_odds = [f"{p['book']}:{p['odds']}" for p in props[prop_key] if p['player'] == prop['player'] and p['pick'] == prop['pick']]
                        lines.append(f"    {prop['player']} {prop['pick']} (line:{prop['line']}) | {' | '.join(book_odds)}")
    return '\n'.join(lines)


def _number(value):
    try:
        return float(str(value).replace("−", "-").replace("+", ""))
    except (TypeError, ValueError):
        return None


def _price(value):
    number = _number(value)
    return number if number is not None else -10000


def _lotto_grade(edge):
    edge = abs(float(edge or 0))
    if edge >= 1.5:
        return "Strong"
    if edge >= 0.75:
        return "Moderate"
    if edge >= 0.25:
        return "Lean"
    return "Forced side"


def build_mlb_lotto_boards(parsed_data, odds_data):
    """Create one model-backed run line and total for every MLB game."""
    projection_index = {}
    for game in parsed_data.get("games", []):
        away = str(game.get("away_team", "")).upper().strip()
        home = str(game.get("home_team", "")).upper().strip()
        away_runs = _number(game.get("away_proj_runs"))
        home_runs = _number(game.get("home_proj_runs"))
        if away and home:
            projection_index[frozenset((away, home))] = {
                "away": away, "home": home,
                "away_runs": away_runs, "home_runs": home_runs,
                "model_winner": game.get("model_winner"),
                "models_agree": game.get("models_agree"),
                "projection_source": game.get("projection_source"),
            }

    spread_board, total_board = [], []
    for game in (odds_data or {}).get("games", []):
        away_name = game.get("away_team", "")
        home_name = game.get("home_team", "")
        matchup = f"{away_name} @ {home_name}"
        away_abbr = MLB_TEAM_ABBREVIATIONS.get(away_name)
        home_abbr = MLB_TEAM_ABBREVIATIONS.get(home_name)
        projection = projection_index.get(frozenset((away_abbr, home_abbr)))
        spread_options, total_options = [], []

        for book, market in game.get("odds_by_book", {}).items():
            if not isinstance(market, dict) or not projection:
                continue
            away_runs = projection["away_runs"] if projection["away"] == away_abbr else projection["home_runs"]
            home_runs = projection["home_runs"] if projection["home"] == home_abbr else projection["away_runs"]

            for team_name, team_abbr, line_key, odds_key in (
                (away_name, away_abbr, "spread_away", "spread_away_odds"),
                (home_name, home_abbr, "spread_home", "spread_home_odds"),
            ):
                if projection.get("model_winner") and team_abbr != projection["model_winner"]:
                    continue
                line = _number(market.get(line_key))
                if line is None:
                    continue
                margin = None
                if away_runs is not None and home_runs is not None:
                    margin = (away_runs - home_runs) if team_abbr == away_abbr else (home_runs - away_runs)
                edge = (margin + line) if margin is not None else 0.0
                spread_options.append((line, _price(market.get(odds_key)), {
                    "game": matchup,
                    "selection": f"{team_name} {line:+g}",
                    "team": team_name,
                    "line": line,
                    "best_book": book,
                    "best_odds": market.get(odds_key),
                    "projected_margin": round(margin, 2) if margin is not None else None,
                    "model_edge": round(edge, 2) if margin is not None else None,
                    "model_winner": projection.get("model_winner"),
                    "confidence": _lotto_grade(edge) if margin is not None else "PropFinder winner lean",
                    "official_pick": False,
                    "track_result": False,
                }))

            total = _number(market.get("total_line"))
            if total is not None and away_runs is not None and home_runs is not None:
                projected_total = away_runs + home_runs
                direction = "Over" if projected_total >= total else "Under"
                edge = abs(projected_total - total)
                odds_key = "over_odds" if direction == "Over" else "under_odds"
                total_options.append((edge, _price(market.get(odds_key)), {
                    "game": matchup,
                    "selection": f"{direction} {total:g}",
                    "over_under": direction,
                    "line": total,
                    "best_book": book,
                    "best_odds": market.get(odds_key),
                    "projected_total": round(projected_total, 2),
                    "model_edge": round(edge, 2),
                    "confidence": _lotto_grade(edge),
                    "official_pick": False,
                    "track_result": False,
                }))

        unavailable = {
            "game": matchup,
            "selection": "No verified model/line",
            "available": False,
            "official_pick": False,
            "track_result": False,
        }
        spread_board.append(max(spread_options, key=lambda item: (item[0], item[1]))[2] if spread_options else dict(unavailable))

        # The current PropFinder winner cards no longer publish projected runs.
        # When that happens, use the no-vig sportsbook consensus for an
        # entertainment-only O/U lean and label it honestly as market-based.
        if not total_options:
            consensus = []
            for book, market in game.get("odds_by_book", {}).items():
                total = _number(market.get("total_line")) if isinstance(market, dict) else None
                over_odds = _number(market.get("over_odds")) if isinstance(market, dict) else None
                under_odds = _number(market.get("under_odds")) if isinstance(market, dict) else None
                if total is None or over_odds is None or under_odds is None:
                    continue
                over_p, under_p = _american_implied(over_odds), _american_implied(under_odds)
                denominator = over_p + under_p
                if denominator:
                    consensus.append((book, total, over_odds, under_odds, over_p / denominator))
            if consensus:
                average_over = sum(item[4] for item in consensus) / len(consensus)
                direction = "Over" if average_over >= 0.5 else "Under"
                choices = []
                for book, total, over_odds, under_odds, _ in consensus:
                    odds = over_odds if direction == "Over" else under_odds
                    line_value = -total if direction == "Over" else total
                    choices.append((line_value, _price(odds), book, total, odds))
                _, _, book, total, odds = max(choices, key=lambda item: (item[0], item[1]))
                total_options.append((abs(average_over - 0.5), _price(odds), {
                    "game": matchup,
                    "selection": f"{direction} {total:g}",
                    "over_under": direction,
                    "line": total,
                    "best_book": book,
                    "best_odds": int(odds) if float(odds).is_integer() else odds,
                    "market_consensus_probability": round((average_over if direction == "Over" else 1 - average_over) * 100, 1),
                    "model_edge": None,
                    "confidence": "Consensus market lean",
                    "official_pick": False,
                    "track_result": False,
                }))
        total_board.append(max(total_options, key=lambda item: (item[0], item[1]))[2] if total_options else dict(unavailable))

    return spread_board, total_board


def _american_implied(odds):
    odds = _number(odds)
    if odds is None or odds == 0:
        return 0.0
    return (-odds / (-odds + 100)) if odds < 0 else (100 / (odds + 100))


def build_mlb_hr_board(odds_data):
    """Choose one sportsbook-listed home-run hitter from every MLB game."""
    props_by_game = (odds_data or {}).get("player_props", {})
    board = []
    for game in (odds_data or {}).get("games", []):
        away = game.get("away_team", "")
        home = game.get("home_team", "")
        matchup = f"{away} @ {home}"
        compact_matchup = f"{away}@{home}".replace(" ", "").lower()
        game_props = {}
        for key, value in props_by_game.items():
            if str(key).replace(" ", "").lower() == compact_matchup:
                game_props = value or {}
                break

        players = {}
        for prop in game_props.get("hr", []):
            if not isinstance(prop, dict):
                continue
            raw_player = str(prop.get("player", "")).strip()
            raw_pick = str(prop.get("pick", "")).strip()
            direction_words = {"over", "under", "yes", "no"}
            if raw_player.lower() in direction_words and raw_pick.lower() not in direction_words:
                player, direction = raw_pick, raw_player
            else:
                player, direction = raw_player, raw_pick
            if not player or direction.lower() in {"under", "no"}:
                continue
            line = _number(prop.get("line"))
            # A standard anytime-HR selection is Over 0.5. Exclude 2+ HR
            # alternate lines (for example Over 1.5 at +2000).
            if line is not None and abs(line - 0.5) > 0.001:
                continue
            odds = _number(prop.get("odds"))
            if odds is None:
                continue
            offer = {
                "book": prop.get("book"),
                "odds": int(odds) if odds.is_integer() else odds,
                "implied": _american_implied(odds),
            }
            existing = players.setdefault(player, [])
            if not any(item["book"] == offer["book"] and item["odds"] == offer["odds"] for item in existing):
                existing.append(offer)

        if not players:
            board.append({
                "game": matchup,
                "selection": "No verified home-run market available",
                "available": False,
                "official_pick": False,
                "track_result": False,
            })
            continue

        ranked = []
        for player, offers in players.items():
            consensus = sum(o["implied"] for o in offers) / len(offers)
            best = max(offers, key=lambda o: _price(o["odds"]))
            ranked.append((consensus, _price(best["odds"]), player, best, len(offers)))
        consensus, _, player, best, book_count = max(ranked, key=lambda item: (item[0], item[1]))
        board.append({
            "game": matchup,
            "selection": f"{player} to hit a home run",
            "player": player,
            "best_book": best["book"],
            "best_odds": best["odds"],
            "market_implied_probability": round(consensus * 100, 1),
            "books_compared": book_count,
            "confidence": "Market favorite",
            "official_pick": False,
            "track_result": False,
        })
    return board

def build_prompt(parsed_data, odds_data, scrape_date):
    games_text = json.dumps(parsed_data.get('games', []), indent=2)
    weather_text = json.dumps(parsed_data.get('weather', [])[:15], indent=2)
    hr_text = parsed_data.get('hr_matchups_text', '')[:3000]
    pitcher_text = json.dumps(parsed_data.get('pitchers', [])[:20], indent=2)
    park_text = json.dumps(parsed_data.get('park_factors', [])[:15], indent=2)
    exit_velo_text = parsed_data.get('exit_velo_text', '')[:1500]
    odds_text = format_odds_for_prompt(odds_data)
    news_data = load_news(scrape_date, sport="mlb")
    news_text = format_news_for_prompt(news_data)

    return f"""You are an elite MLB sports betting analyst focused on HIGH-CONVICTION, HIGH-VALUE plays only. Today is {scrape_date}.

Analyze ALL the data below across every game and every prop category (HR, Hits, Total Bases, Strikeouts, Game ML/Spread/OU).
Your job is to find the 2 single best bets of the entire slate — NOT one per category, just the 2 best overall.

{odds_text}

== GAME PROJECTIONS (PropFinder Model) ==
{games_text}

== BALLPARK WEATHER ==
{weather_text}

== HR MATCHUPS & BATTER DATA ==
{hr_text}

== PITCHER SUMMARY ==
{pitcher_text}

== PARK FACTORS ==
{park_text}

== EXIT VELO (Recent) ==
{exit_velo_text}

=== RECENT NEWS & INJURY CONTEXT ===
{news_text}

SELECTION RULES — READ CAREFULLY:
1. Evaluate ALL prop categories and game bets across the entire slate
2. Select EXACTLY 5 picks total — the 5 best plays you can find anywhere on the slate
3. ODDS FILTER (HARD RULE): Only picks where the best available odds are between -130 and +125 (inclusive)
   - ALLOWED examples: -130, -120, -110, -105, +100, +110, +120, +125
   - REJECTED examples: -140, -150, -200, +130, +150, +200, +300
   - If no pick meets the filter, return the 3-4 picks closest to this range and note it
4. Each pick must have MULTIPLE converging edges — pitcher matchup + recent form + park/weather + favorable odds
5. Do NOT force picks into categories — find the 2 best plays wherever they are
6. Rank by overall confidence — best pick is rank 1

WHAT MAKES A GREAT PICK:
- Clear statistical edge (hard-hit rate, K%, barrel rate, WHIFF%, exit velo, etc.)
- Odds in the sweet spot (-130 to +125) — value without heavy juice
- Multiple converging factors, not just one isolated reason
- No significant injury or lineup concerns in the news
- Pitcher you are betting against has a clear exploitable weakness

REQUIRED OUTPUT FORMAT (JSON only, no markdown, no extra text):
{{
  "top_picks": [
    {{
      "rank": 1,
      "category": "HR | Hits | Total Bases | Strikeouts | Game ML | Game Spread | Game OU",
      "player_name": "name (or team name for game picks)",
      "pick_type": "batter | pitcher | team",
      "game": "AWAY @ HOME",
      "game_time": "time",
      "best_book": "FD | MGM | CZS | SCR",
      "best_odds": "+110",
      "fd_odds": "+110",
      "mgm_odds": null,
      "czs_odds": null,
      "scr_odds": null,
      "fd_line": "0.5",
      "over_under_pick": "over | under | null",
      "confidence_score": 88,
      "confidence_tier": "Elite | High | Medium",
      "key_factors": ["factor1", "factor2", "factor3"],
      "reasoning": "2-3 sentences explaining why this is one of the 2 best plays on the slate today",
      "line_shop_note": "note if meaningful odds difference exists across books, or null"
    }}
  ],
  "daily_summary": "1-2 sentence overview of today's slate and why these 2 picks stand out above the rest",
  "best_bet": "The single best pick in one sentence"
}}

Return ONLY valid JSON. No markdown fences, no explanation outside JSON."""

# ─────────────────────────────────────────────
# NRFI PICKS
# ─────────────────────────────────────────────

def build_nrfi_prompt(nrfi_data, scrape_date):
    team_records = '\n'.join(nrfi_data.get('team_records', [])[:35])
    batting_records = '\n'.join(nrfi_data.get('batting_records', [])[:35])
    pitcher_records = '\n'.join(nrfi_data.get('pitcher_records', [])[:35])

    matchups = nrfi_data.get('matchups', [])
    if matchups and isinstance(matchups[0], list):
        matchups_text = '\n\n'.join(['\n'.join(m) for m in matchups])
    elif matchups and isinstance(matchups[0], dict):
        matchups_text = matchups[0].get('raw_text', '')[:5000]
    else:
        matchups_text = str(matchups)[:5000]

    nrfi_scores = nrfi_data.get('nrfi_scores', [])
    scores_text = ', '.join(str(s) for s in nrfi_scores) if nrfi_scores else 'See matchup cards'

    return f"""You are an elite MLB NRFI/YRFI betting analyst. Today is {scrape_date}.

Analyze the NRFI/YRFI research data below and pick the 1 best play for today (NRFI or YRFI).
Only pick a play you have very high conviction in. Quality over quantity.

== TODAY'S MATCHUPS ==
Each card shows Team NRFI%, L-10, Pitcher NRFI%+Streak, Batting NRFI%+Streak, and NRFI Score.
Higher NRFI Score = stronger NRFI lean. Lower score = YRFI lean.
{matchups_text}

== NRFI COMPOSITE SCORES ==
{scores_text}

== TEAM RECORDS (Season NRFI%) ==
{team_records}

== BATTING RECORDS (Season Batting NRFI%) ==
{batting_records}

== PITCHER RECORDS (Season Pitcher NRFI%) ==
{pitcher_records}

SELECTION RULES:
- Pick EXACTLY 2 play (NRFI or YRFI) — your two highest-conviction play
- NRFI plays: NRFI Score 78+, both pitchers strong NRFI% with active streaks, both teams batting NRFI% above 55%
- YRFI plays: NRFI Score below 50, pitchers with high 1st inning RA, hot-hitting lineups, active YRFI streaks
- If nothing is truly elite, return your single best available play anyway

REQUIRED OUTPUT FORMAT (JSON only, no markdown):
{{
  "nrfi_picks": [
    {{"rank":1,"pick":"NRFI","game":"AWAY @ HOME","away_pitcher":"name","home_pitcher":"name","nrfi_score":83.4,"confidence_tier":"Elite | High | Medium","away_team_nrfi_pct":"58%","home_team_nrfi_pct":"61%","away_pitcher_nrfi_pct":"100%","home_pitcher_nrfi_pct":"100%","away_pitcher_streak":"7 NRFI","home_pitcher_streak":"3 NRFI","key_factors":["f1","f2","f3"],"reasoning":"2-3 sentences"}}
  ]
}}

Return ONLY valid JSON. No markdown, no extra text."""


def generate_nrfi_picks(nrfi_data, scrape_date, api_client=None):
    if not nrfi_data or not nrfi_data.get('matchups'):
        print("   ⚠️ No NRFI matchup data available")
        return []

    print("\n🎰 Generating NRFI pick with Claude...")
    prompt = build_nrfi_prompt(nrfi_data, scrape_date)
    _client = api_client or client

    try:
        message = _client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        data = json.loads(raw)
        picks = data.get('nrfi_picks', [])
        print(f"   ✅ {len(picks)} NRFI pick(s) generated")
        for pick in picks:
            print(f"   [{pick.get('confidence_tier','')}] {pick.get('pick','')} — {pick.get('game','')} (Score: {pick.get('nrfi_score','')})")
        return picks
    except json.JSONDecodeError as e:
        print(f"   ❌ NRFI JSON parse error: {e}")
        return []
    except Exception as e:
        print(f"   ❌ NRFI analyzer error: {e}")
        return []

# ─────────────────────────────────────────────
# PRINT HELPERS
# ─────────────────────────────────────────────

def print_top_picks(picks):
    print(f"\n{'='*50}")
    print(f"⭐ TODAY'S TOP PICKS ({len(picks)} picks)")
    print(f"{'='*50}")
    if not picks:
        print("  No picks available today")
        return
    for pick in picks:
        rank = pick.get('rank', '')
        tier = pick.get('confidence_tier', '')
        player = pick.get('player_name', 'N/A')
        cat = pick.get('category', '')
        game = pick.get('game', '')
        game_time = pick.get('game_time', '')
        best_book = pick.get('best_book', '')
        best_odds = pick.get('best_odds', '')
        fd_odds = pick.get('fd_odds')
        mgm_odds = pick.get('mgm_odds')
        czs_odds = pick.get('czs_odds')
        scr_odds = pick.get('scr_odds')
        line = pick.get('fd_line')
        over_under = pick.get('over_under_pick', '')
        shop = pick.get('line_shop_note')

        book_odds = []
        if fd_odds and str(fd_odds) != 'None': book_odds.append(f"FD:{fd_odds}")
        if mgm_odds and str(mgm_odds) != 'None': book_odds.append(f"MGM:{mgm_odds}")
        if czs_odds and str(czs_odds) != 'None': book_odds.append(f"CZS:{czs_odds}")
        if scr_odds and str(scr_odds) != 'None': book_odds.append(f"SCR:{scr_odds}")

        if line and over_under:
            line_display = f"{over_under.upper()} {line}"
        elif line:
            line_display = f"Line: {line}"
        elif over_under:
            line_display = over_under.upper()
        else:
            line_display = "To Hit"

        print(f"\n  #{rank} [{tier}] {player} — {cat} | {line_display}")
        print(f"     📅 {game} | {game_time}")
        print(f"     📖 Best: {best_book} {best_odds} | {' | '.join(book_odds) if book_odds else 'No odds found'}")
        if shop: print(f"     💡 {shop}")
        print(f"     📝 {pick.get('reasoning','')[:150]}...")
        factors = pick.get('key_factors', [])
        if factors: print(f"     🔑 {' • '.join(factors[:3])}")

def analyze_and_generate_picks(parsed_data, odds_data, scrape_date):
    print(f"\n{'='*50}")
    print(f"🤖 Claude Haiku analyzing {scrape_date} slate...")
    print(f"{'='*50}\n")

    prompt = build_prompt(parsed_data, odds_data, scrape_date)
    try:
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw_response = message.content[0].text
        print(f"✅ Claude responded ({len(raw_response)} chars)")
        print(f"💰 Tokens used: {message.usage.input_tokens} in / {message.usage.output_tokens} out")

        clean = raw_response.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip()
        picks_data = json.loads(clean)
        spread_board, total_board = build_mlb_lotto_boards(
            parsed_data, odds_data
        )
        picks_data["lotto_spread_board"] = spread_board
        picks_data["lotto_total_board"] = total_board
        picks_data["lotto_hr_board"] = build_mlb_hr_board(odds_data)
        picks_data["lotto_notice"] = (
            "Entertainment-only side boards; excluded from grading "
            "and official records."
        )
        print(f"✅ JSON parsed successfully")
        print(f"\n🎯 BEST BET: {picks_data.get('best_bet','N/A')}")
        print(f"📋 {picks_data.get('daily_summary','N/A')}")
        print_top_picks(picks_data.get('top_picks', []))
        return picks_data
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"❌ Claude API error: {e}")
        return None


if __name__ == "__main__":
    from parser import run_parser
    scrape_date = datetime.now().strftime("%Y-%m-%d")
    raw_data = {}
    for tab in ['hr_matchups','exit_velo','pitcher_summary','park_factors','weather','projections']:
        filepath = f"logs/{scrape_date}_{tab}.json"
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                raw_data[tab] = json.load(f)
    odds_data = load_odds(scrape_date)
    parsed = run_parser(raw_data, scrape_date)
    picks = analyze_and_generate_picks(parsed, odds_data, scrape_date)
    if picks:
        with open(f"logs/{scrape_date}_picks.json", 'w') as f:
            json.dump(picks, f, indent=2)
        print(f"\n💾 Picks saved")
