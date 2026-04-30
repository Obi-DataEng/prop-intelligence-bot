import anthropic
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from news_fetcher import load_news, format_news_for_prompt

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def load_odds(scrape_date):
    """Load odds data from odds_fetcher output"""
    filepath = f"logs/{scrape_date}_odds.json"
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            data = json.load(f)
        print(f"✅ Odds loaded: {len(data.get('games', []))} games, "
              f"{len(data.get('player_props', {}))} games with props")
        return data
    else:
        print(f"⚠️  No odds file found at {filepath}")
        print(f"   Run odds_fetcher.py first")
        return None

def format_odds_for_prompt(odds_data):
    """Format odds data into clean text for Claude"""
    if not odds_data:
        return "No odds data available."

    lines = []

    lines.append("== GAME ODDS (FD=FanDuel, MGM=BetMGM, CZS=Caesars, SCR=theScore) ==")
    for game in odds_data.get('games', []):
        away = game['away_team']
        home = game['home_team']
        lines.append(f"\n{away} @ {home}")
        for book, odds in game.get('odds_by_book', {}).items():
            lines.append(
                f"  {book}: ML {odds['ml_away']}/{odds['ml_home']} | "
                f"RL {odds['spread_away']}({odds['spread_away_odds']}) | "
                f"O/U {odds['total_line']} O:{odds['over_odds']} U:{odds['under_odds']}"
            )

    lines.append("\n== PLAYER PROPS BY GAME ==")
    for matchup, props in odds_data.get('player_props', {}).items():
        lines.append(f"\n{matchup}:")

        if props['hr']:
            lines.append("  HR:")
            seen = set()
            for prop in props['hr']:
                key = f"{prop['player']}-{prop['pick']}"
                if key not in seen:
                    seen.add(key)
                    book_odds = [
                        f"{p['book']}:{p['odds']}"
                        for p in props['hr']
                        if p['player'] == prop['player']
                        and p['pick'] == prop['pick']
                    ]
                    lines.append(f"    {prop['player']} {prop['pick']} "
                               f"(line:{prop['line']}) | {' | '.join(book_odds)}")

        if props['hits']:
            lines.append("  Hits:")
            seen = set()
            for prop in props['hits']:
                key = f"{prop['player']}-{prop['pick']}"
                if key not in seen:
                    seen.add(key)
                    book_odds = [
                        f"{p['book']}:{p['odds']}"
                        for p in props['hits']
                        if p['player'] == prop['player']
                        and p['pick'] == prop['pick']
                    ]
                    lines.append(f"    {prop['player']} {prop['pick']} "
                               f"(line:{prop['line']}) | {' | '.join(book_odds)}")

        if props['total_bases']:
            lines.append("  Total Bases:")
            seen = set()
            for prop in props['total_bases']:
                key = f"{prop['player']}-{prop['pick']}"
                if key not in seen:
                    seen.add(key)
                    book_odds = [
                        f"{p['book']}:{p['odds']}"
                        for p in props['total_bases']
                        if p['player'] == prop['player']
                        and p['pick'] == prop['pick']
                    ]
                    lines.append(f"    {prop['player']} {prop['pick']} "
                               f"(line:{prop['line']}) | {' | '.join(book_odds)}")

        if props['pitcher_k']:
            lines.append("  Pitcher Ks:")
            seen = set()
            for prop in props['pitcher_k']:
                key = f"{prop['player']}-{prop['pick']}"
                if key not in seen:
                    seen.add(key)
                    book_odds = [
                        f"{p['book']}:{p['odds']}"
                        for p in props['pitcher_k']
                        if p['player'] == prop['player']
                        and p['pick'] == prop['pick']
                    ]
                    lines.append(f"    {prop['player']} {prop['pick']} "
                               f"(line:{prop['line']}) | {' | '.join(book_odds)}")

        if props['batter_k']:
            lines.append("  Batter Ks:")
            seen = set()
            for prop in props['batter_k']:
                key = f"{prop['player']}-{prop['pick']}"
                if key not in seen:
                    seen.add(key)
                    book_odds = [
                        f"{p['book']}:{p['odds']}"
                        for p in props['batter_k']
                        if p['player'] == prop['player']
                        and p['pick'] == prop['pick']
                    ]
                    lines.append(f"    {prop['player']} {prop['pick']} "
                               f"(line:{prop['line']}) | {' | '.join(book_odds)}")

    return '\n'.join(lines)

def build_prompt(parsed_data, odds_data, scrape_date):
    """Build the prompt for Claude"""

    games_text = json.dumps(parsed_data.get('games', []), indent=2)
    weather_text = json.dumps(parsed_data.get('weather', [])[:15], indent=2)
    hr_text = parsed_data.get('hr_matchups_text', '')[:3000]
    pitcher_text = json.dumps(parsed_data.get('pitchers', [])[:20], indent=2)
    park_text = json.dumps(parsed_data.get('park_factors', [])[:15], indent=2)
    exit_velo_text = parsed_data.get('exit_velo_text', '')[:1500]
    odds_text = format_odds_for_prompt(odds_data)
    news_data = load_news(scrape_date, sport="mlb")  # or "nba"
    news_text = format_news_for_prompt(news_data)

    prompt = f"""You are an elite MLB sports betting analyst. Today is {scrape_date}.

Analyze the following data and generate the BEST picks for today organized by category.

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

SELECTION RULES:
- Generate EXACTLY 8 total picks across ALL categories combined
- Only include the absolute highest confidence plays regardless of category
- Do NOT force picks into every category — leave categories empty if no strong plays exist
- ONLY include picks where you have actual odds data from the odds section above
- If no odds exist for a prop skip it entirely
- For each pick choose the BEST book (highest payout for same line)
- Flag line shopping opportunities where books differ significantly
- HR picks: prioritize high Barrel%, HardHit%, favorable pitcher HR/9, HR/FB%, park factor, wind
- Hits picks: high BA, wOBA, low pitcher WHIP
- Total Bases: combine HR and hits factors
- K props: pitcher K/9, batter K%, weak contact rates
- Game picks: large proj run differential, strong pitcher matchup, weather factors
- Rank all 7 picks by confidence — best pick first
LASER PICKS: Identify 2 players most likely to hit a ball 110+ mph exit velocity today.
Prioritize players who:
- Have recent BBE at 110+ mph in the exit velo data
- Have elite barrel rates (15%+) and hard hit rates (50%+)
- Face pitchers who allow high hard hit rates
- Play in HR-friendly parks (park factor 1.10+)
- Play in warm weather (65°F+)
Note: These are NOT tied to odds — purely data-driven laser candidates.

REQUIRED OUTPUT FORMAT (JSON only, no other text, no markdown):
{{
    "laser_picks": [
    {{
      "rank": 1,
      "player_name": "name",
      "team": "team name",
      "opponent": "opponent name",
      "game": "AWAY @ HOME",
      "game_time": "time",
      "confidence_tier": "Elite | High | Medium",
      "recent_max_ev": "115.3 mph on 4/21",
      "avg_exit_velo": "94.5 mph",
      "barrel_rate": "18%",
      "hard_hit_rate": "55%",
      "pitcher_hard_hit_allowed": "42%",
      "park_factor_hr": 1.15,
      "key_factors": ["factor 1", "factor 2", "factor 3"],
      "reasoning": "2-3 sentence explanation of why this player is likely to hit 110+ EV today"
    }}
  ],
  "hr_picks": [
    {{
      "rank": 1,
      "player_name": "name",
      "team": "team name",
      "opponent": "opponent name",
      "game": "AWAY @ HOME",
      "game_time": "time",
      "best_book": "FD | MGM | CZS | SCR",
      "fd_odds": "odds or null",
      "mgm_odds": "odds or null",
      "czs_odds": "odds or null",
      "scr_odds": "odds or null",
      "fd_line": "line value or null",
      "confidence_score": 85,
      "confidence_tier": "Elite | High | Medium",
      "key_factors": ["factor 1", "factor 2", "factor 3"],
      "reasoning": "2-3 sentence explanation",
      "line_shop_note": "note or null"
    }}
  ],
  "hits_picks": [
    {{
      "rank": 1,
      "player_name": "name",
      "team": "team name",
      "opponent": "opponent name",
      "game": "AWAY @ HOME",
      "game_time": "time",
      "best_book": "FD | MGM | CZS | SCR",
      "fd_odds": "odds or null",
      "mgm_odds": "odds or null",
      "czs_odds": "odds or null",
      "scr_odds": "odds or null",
      "fd_line": "line value or null",
      "over_under_pick": "over or under",
      "confidence_score": 80,
      "confidence_tier": "Elite | High | Medium",
      "key_factors": ["factor 1", "factor 2", "factor 3"],
      "reasoning": "2-3 sentence explanation",
      "line_shop_note": "note or null"
    }}
  ],
  "total_bases_picks": [
    {{
      "rank": 1,
      "player_name": "name",
      "team": "team name",
      "opponent": "opponent name",
      "game": "AWAY @ HOME",
      "game_time": "time",
      "best_book": "FD | MGM | CZS | SCR",
      "fd_odds": "odds or null",
      "mgm_odds": "odds or null",
      "czs_odds": "odds or null",
      "scr_odds": "odds or null",
      "fd_line": "line value",
      "over_under_pick": "over or under",
      "confidence_score": 78,
      "confidence_tier": "Elite | High | Medium",
      "key_factors": ["factor 1", "factor 2", "factor 3"],
      "reasoning": "2-3 sentence explanation",
      "line_shop_note": "note or null"
    }}
  ],
  "strikeout_picks": [
    {{
      "rank": 1,
      "player_name": "name",
      "pick_type": "pitcher or batter",
      "team": "team name",
      "opponent": "opponent name",
      "game": "AWAY @ HOME",
      "game_time": "time",
      "best_book": "FD | MGM | CZS | SCR",
      "fd_odds": "odds or null",
      "mgm_odds": "odds or null",
      "czs_odds": "odds or null",
      "scr_odds": "odds or null",
      "fd_line": "line value",
      "over_under_pick": "over or under",
      "confidence_score": 75,
      "confidence_tier": "Elite | High | Medium",
      "key_factors": ["factor 1", "factor 2", "factor 3"],
      "reasoning": "2-3 sentence explanation",
      "line_shop_note": "note or null"
    }}
  ],
  "game_picks": [
    {{
      "rank": 1,
      "prop_category": "ML | OU | Spread",
      "game": "AWAY @ HOME",
      "game_time": "time",
      "pick": "team name or Over/Under",
      "best_book": "FD | MGM | CZS | SCR",
      "fd_odds": "odds or null",
      "mgm_odds": "odds or null",
      "czs_odds": "odds or null",
      "scr_odds": "odds or null",
      "fd_line": "line value or null",
      "confidence_score": 72,
      "confidence_tier": "Elite | High | Medium",
      "key_factors": ["factor 1", "factor 2", "factor 3"],
      "reasoning": "2-3 sentence explanation",
      "line_shop_note": "note or null"
    }}
  ],
  "best_parlay": {{
    "legs": ["pick description 1", "pick description 2", "pick description 3"],
    "reasoning": "why these combine well",
    "estimated_odds": "combined odds estimate"
  }},
  "daily_summary": "2-3 sentence overview of today's slate",
  "best_bet": "single best pick of the day in one sentence"
}}

Return ONLY valid JSON. No markdown fences, no explanation outside JSON."""

    return prompt

def print_picks_section(title, emoji, picks, show_pick_type=False):
    """Print a formatted section of picks"""
    print(f"\n{'='*50}")
    print(f"{emoji} {title} ({len(picks)} picks)")
    print(f"{'='*50}")

    if not picks:
        print("  No picks available for this category")
        return

    for pick in picks:
        player = pick.get('player_name') or pick.get('pick', 'Game Pick')
        rank = pick.get('rank', '')
        tier = pick.get('confidence_tier', '')
        best_book = pick.get('best_book', '')
        fd_odds = pick.get('fd_odds')
        mgm_odds = pick.get('mgm_odds')
        czs_odds = pick.get('czs_odds')
        scr_odds = pick.get('scr_odds')
        line = pick.get('fd_line')
        over_under = pick.get('over_under_pick', '')
        shop = pick.get('line_shop_note')
        game = pick.get('game', '')
        game_time = pick.get('game_time', '')
        pick_type = pick.get('pick_type', '')
        prop_cat = pick.get('prop_category', '')

        # Build odds string — only show books with actual odds
        book_odds = []
        if fd_odds and str(fd_odds) != 'None':
            book_odds.append(f"FD:{fd_odds}")
        if mgm_odds and str(mgm_odds) != 'None':
            book_odds.append(f"MGM:{mgm_odds}")
        if czs_odds and str(czs_odds) != 'None':
            book_odds.append(f"CZS:{czs_odds}")
        if scr_odds and str(scr_odds) != 'None':
            book_odds.append(f"SCR:{scr_odds}")

        # Format line display
        if line and over_under:
            line_display = f"{over_under.upper()} {line}"
        elif line:
            line_display = f"Line: {line}"
        elif over_under:
            line_display = over_under.upper()
        else:
            line_display = "To Hit"

        label = f"{prop_cat} " if prop_cat else ""
        type_label = f" [{pick_type}]" if show_pick_type and pick_type else ""

        print(f"\n  #{rank} [{tier}] {player}{type_label} — {label}{line_display}")
        print(f"     📅 {game} | {game_time}")
        print(f"     📖 Best: {best_book} | "
              f"{' | '.join(book_odds) if book_odds else 'No odds found'}")
        if shop:
            print(f"     💡 {shop}")
        print(f"     📝 {pick.get('reasoning', '')[:130]}...")
        factors = pick.get('key_factors', [])
        if factors:
            print(f"     🔑 {' • '.join(factors[:3])}")

def analyze_and_generate_picks(parsed_data, odds_data, scrape_date):
    """Send data to Claude Haiku and get picks"""
    print(f"\n{'='*50}")
    print(f"🤖 Claude Haiku analyzing {scrape_date} slate...")
    print(f"{'='*50}\n")

    prompt = build_prompt(parsed_data, odds_data, scrape_date)

    try:
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw_response = message.content[0].text
        print(f"✅ Claude responded ({len(raw_response)} chars)")
        print(f"💰 Tokens used: {message.usage.input_tokens} in / "
              f"{message.usage.output_tokens} out")

        # Strip markdown if present
        clean = raw_response.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip()

        picks_data = json.loads(clean)
        print(f"✅ JSON parsed successfully")

        # Summary
        print(f"\n🎯 BEST BET: {picks_data.get('best_bet', 'N/A')}")
        print(f"📋 {picks_data.get('daily_summary', 'N/A')}")

        # Print all sections
        print_picks_section("HOME RUN PICKS", "💣",
                           picks_data.get('hr_picks', []))
        print_picks_section("HITS PICKS", "🎯",
                           picks_data.get('hits_picks', []))
        print_picks_section("TOTAL BASES PICKS", "📊",
                           picks_data.get('total_bases_picks', []))
        print_picks_section("STRIKEOUT PICKS", "🔥",
                           picks_data.get('strikeout_picks', []),
                           show_pick_type=True)
        print_picks_section("GAME PICKS", "💰",
                           picks_data.get('game_picks', []))

        # Best parlay
        parlay = picks_data.get('best_parlay', {})
        if parlay:
            print(f"\n{'='*50}")
            print(f"🎰 BEST PARLAY")
            print(f"{'='*50}")
            for leg in parlay.get('legs', []):
                print(f"  + {leg}")
            print(f"  Est. Odds: {parlay.get('estimated_odds', 'N/A')}")
            print(f"  📝 {parlay.get('reasoning', '')}")

        # Total count
        total = (len(picks_data.get('hr_picks', [])) +
                 len(picks_data.get('hits_picks', [])) +
                 len(picks_data.get('total_bases_picks', [])) +
                 len(picks_data.get('strikeout_picks', [])) +
                 len(picks_data.get('game_picks', [])))
        print(f"\n📊 Total picks generated: {total}")

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

    # Load PropFinder data
    tabs = ['hr_matchups', 'exit_velo', 'pitcher_summary',
            'park_factors', 'weather', 'projections']
    for tab in tabs:
        filepath = f"logs/{scrape_date}_{tab}.json"
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                raw_data[tab] = json.load(f)
            print(f"📂 Loaded {tab}")
        else:
            print(f"⚠️  Missing {filepath}")

    # Load odds data
    print(f"\n💰 Loading odds data...")
    odds_data = load_odds(scrape_date)

    # Parse PropFinder data
    parsed = run_parser(raw_data, scrape_date)

    # Generate picks
    picks = analyze_and_generate_picks(parsed, odds_data, scrape_date)

    if picks:
        output_file = f"logs/{scrape_date}_picks.json"
        with open(output_file, 'w') as f:
            json.dump(picks, f, indent=2)
        print(f"\n💾 Picks saved to {output_file}")