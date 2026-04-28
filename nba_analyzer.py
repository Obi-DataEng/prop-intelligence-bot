import anthropic
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def load_nba_data(scrape_date):
    data = {}
    files = [
        "nba_player_stats",
        "nba_def_matchups",
        "nba_hit_rate",
        "nba_injury_reports",
        "nba_lineups",
        "nba_team_stats",
        "nba_research"      # ← ADD THIS
    ]
    for name in files:
        filepath = f"logs/{scrape_date}_{name}.json"
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data[name] = json.load(f)
            print(f"   📂 Loaded {name}")
        else:
            print(f"   ⚠️ Missing {name}")
            data[name] = {}
    return data


def load_nba_odds(scrape_date):
    """Load NBA odds from file"""
    filepath = f"logs/{scrape_date}_nba_odds.json"
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    print("   ⚠️ No NBA odds file found")
    return {}


def format_nba_odds_for_prompt(odds_data):
    """Format NBA odds into readable text for Claude"""
    if not odds_data:
        return "No odds data available"

    text = ""
    games = odds_data.get('games', [])
    player_props = odds_data.get('player_props', {})

    for game in games:
        home = game['home_team']
        away = game['away_team']
        game_key = f"{away}@{home}"
        books = game.get('bookmakers', {})

        text += f"\n{away} @ {home}\n"

        for book, data in books.items():
            text += (f"  {book}: ML {data.get('away_ml','N/A')}/{data.get('home_ml','N/A')} | "
                     f"Spread {data.get('away_spread','N/A')} | "
                     f"O/U {data.get('total','N/A')}\n")

        props = player_props.get(game_key, {})
        if props:
            text += "  PLAYER PROPS:\n"
            for market, players in props.items():
                market_label = {
                    'player_points': 'PTS',
                    'player_rebounds': 'REB',
                    'player_assists': 'AST',
                    'player_threes': '3PM',
                    'player_points_rebounds_assists': 'PRA',
                    'player_points_rebounds': 'PR',
                    'player_points_assists': 'PA',
                    'player_steals': 'STL',
                    'player_blocks': 'BLK'
                }.get(market, market)

                text += f"    {market_label}:\n"
                for player, data in list(players.items())[:8]:
                    line = data.get('line', 'N/A')
                    fd_over = data.get('FD', {}).get('over', 'N/A')
                    mgm_over = data.get('MGM', {}).get('over', 'N/A')
                    czs_over = data.get('CZS', {}).get('over', 'N/A')
                    text += f"      {player} {line} | FD:{fd_over} MGM:{mgm_over} CZS:{czs_over}\n"

    return text[:6000]


def build_nba_prompt(data, odds_text, scrape_date, odds_data=None):
    """Build the Claude prompt with all NBA context"""

    if odds_data is None:
        odds_data = {}

    # Add research data
    research_data = data.get('nba_research', {})
    research_rows = research_data.get('rows', [])
    # Limit to 300 rows to avoid token overload — sorted keeps best rated first
    research_text = '\n'.join(research_rows[:300])

    player_stats_text = data.get('nba_player_stats', {}).get('fullText', '')[:4000]
    def_matchups_text = data.get('nba_def_matchups', {}).get('fullText', '')[:3000]

    hit_rate_data = data.get('nba_hit_rate', {})
    hit_rate_text = ""
    for cat, text in hit_rate_data.items():
        if text:
            hit_rate_text += f"\n=== {cat.upper()} ===\n{text[:800]}\n"
    hit_rate_text = hit_rate_text[:4000]

    injury_text = data.get('nba_injury_reports', {}).get('fullText', '')[:2000]
    team_stats_text = data.get('nba_team_stats', {}).get('fullText', '')[:2000]
    lineups_full = data.get('nba_lineups', {}).get('fullText', '')
    lineups_text = lineups_full[:3000]

    games_today = [
        f"{g['away_team']} @ {g['home_team']}"
        for g in odds_data.get('games', [])
    ]
    games_today_str = '\n'.join(f"  - {g}" for g in games_today) \
                      if games_today else "  No games found"

    prompt = f"""You are an expert NBA sports betting analyst. Analyze today's NBA slate and generate picks.

DATE: {scrape_date}

GAMES BEING PLAYED TODAY ({scrape_date}) — ONLY these games exist:
{games_today_str}

Any player not on these teams today should be ignored entirely.

=== PLAYER STATS (Season Averages) ===
{player_stats_text}

=== DEFENSIVE MATCHUPS (How each defense performs vs each position) ===
{def_matchups_text}

=== HIT RATE MATRIX (Historical prop hit rates this season) ===
{hit_rate_text}

=== NBA RESEARCH (Today's Props — Hit Rates + Odds + Matchup %) ===
COLUMNS: PF_Rating | Team | Pos | Player | Prop | L10_Avg | L5_Avg | Odds | Streak | Matchup | 24-25_Hit% | 25-26_Hit%
{research_text}

=== INJURY REPORTS ===
{injury_text}

=== CONFIRMED LINEUPS ===
{lineups_text}

=== TEAM STATS ===
{team_stats_text}

=== TODAY'S ODDS (Lines + Player Props) ===
{odds_text}

INSTRUCTIONS:
Generate EXACTLY 8 total NBA picks across ALL categories combined for today's games.
Quality over quantity — only the highest confidence plays regardless of category.
Do NOT force picks into every category — leave categories empty if no strong plays exist.

CRITICAL RULE: Only generate picks for games being played on {scrape_date} specifically.
Do NOT generate picks for any other date.
Only include players and games that appear in the TODAY'S ODDS section above.
If a game does not appear in the odds data, it is NOT being played today — ignore it completely.
The odds data is the single source of truth for which games are happening today.

Key factors to analyze:
- Player season averages vs the ACTUAL prop line from the odds data above
- Defensive matchup rank vs the player's position (bad defense = over opportunity)
- Hit rate history — how often has this player hit this line this season
- Injury report — is the opposing star player out (creates scoring opportunities)?
- Confirmed starting lineup — is the player starting?
- Pace of play and team offensive tendencies from team stats
- Line shopping — identify the best book for each pick
- Remember it is playoffs so make sure to look at streaks happening as teams are playing the same team for 7 game series

Only pick games being played TODAY based on the odds data.
Ignore players who are Out on the injury report.
Always reference the actual prop line from the odds data.
Return ONLY valid JSON. No markdown fences, no explanation outside JSON.

Generate picks in this EXACT JSON format with no markdown, no backticks, just pure JSON:

{{
  "slate_summary": "2-3 sentence overview of today's NBA slate and key themes",
  "best_bet": "Single best bet of the day with reasoning",
  "points_picks": [
    {{
      "player_name": "Player Name",
      "team": "TEAM",
      "opponent": "OPP",
      "prop_line": 25.5,
      "over_under": "OVER",
      "best_book": "FD",
      "best_odds": -115,
      "confidence": "Elite/High/Medium",
      "season_avg": 27.2,
      "l5_avg": 28.1,
      "def_rank_vs_pos": "#24 (Bad)",
      "hit_rate_season": "68%",
      "key_factors": ["factor 1", "factor 2", "factor 3"],
      "reasoning": "2-3 sentence reasoning"
    }}
  ],
  "rebounds_picks": [
    {{
      "player_name": "Player Name",
      "team": "TEAM",
      "opponent": "OPP",
      "prop_line": 8.5,
      "over_under": "OVER",
      "best_book": "FD",
      "best_odds": -115,
      "confidence": "High",
      "season_avg": 9.2,
      "l5_avg": 9.8,
      "def_rank_vs_pos": "#18 (Bad)",
      "hit_rate_season": "61%",
      "key_factors": ["factor 1", "factor 2"],
      "reasoning": "2-3 sentence reasoning"
    }}
  ],
  "assists_picks": [
    {{
      "player_name": "Player Name",
      "team": "TEAM",
      "opponent": "OPP",
      "prop_line": 6.5,
      "over_under": "OVER",
      "best_book": "MGM",
      "best_odds": -110,
      "confidence": "High",
      "season_avg": 7.1,
      "l5_avg": 7.4,
      "def_rank_vs_pos": "#22 (Bad)",
      "hit_rate_season": "66%",
      "key_factors": ["factor 1", "factor 2"],
      "reasoning": "2-3 sentence reasoning"
    }}
  ],
  "threes_picks": [
    {{
      "player_name": "Player Name",
      "team": "TEAM",
      "opponent": "OPP",
      "prop_line": 2.5,
      "over_under": "OVER",
      "best_book": "FD",
      "best_odds": -110,
      "confidence": "Medium",
      "season_avg": 2.9,
      "l5_avg": 3.1,
      "def_rank_vs_pos": "#25 (Bad)",
      "hit_rate_season": "58%",
      "key_factors": ["factor 1", "factor 2"],
      "reasoning": "2-3 sentence reasoning"
    }}
  ],
  "combo_picks": [
    {{
      "player_name": "Player Name",
      "team": "TEAM",
      "opponent": "OPP",
      "prop_type": "PRA/PR/PA",
      "prop_line": 40.5,
      "over_under": "OVER",
      "best_book": "FD",
      "best_odds": -115,
      "confidence": "Elite",
      "season_avg": 42.1,
      "l5_avg": 43.2,
      "def_rank_vs_pos": "#28 (Bad)",
      "hit_rate_season": "71%",
      "key_factors": ["factor 1", "factor 2"],
      "reasoning": "2-3 sentence reasoning"
    }}
  ],
  "game_picks": [
    {{
      "game": "Team A @ Team B",
      "pick_type": "ML/Spread/OU",
      "pick": "Team Name or Over/Under",
      "line": -110,
      "best_book": "MGM",
      "confidence": "High",
      "key_factors": ["factor 1", "factor 2"],
      "reasoning": "2-3 sentence reasoning"
    }}
  ],
  "best_parlay": {{
    "legs": ["leg 1 description", "leg 2 description", "leg 3 description"],
    "estimated_odds": "+400",
    "reasoning": "Why these legs correlate"
  }}
}}

SELECTION RULES:
- Generate EXACTLY 7 total picks across ALL categories combined
- Only include the absolute highest confidence plays regardless of category
- Do NOT force picks into every category — leave categories empty if no strong plays exist
- ONLY include picks where you have actual odds data from the odds section above
- If no odds exist for a prop skip it entirely
- For each pick choose the BEST book (highest payout for same line)
- Rank all 7 picks by confidence — best pick first"""

    return prompt


def run_nba_analyzer(scrape_date=None, odds_data=None):
    if not scrape_date:
        scrape_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*50}")
    print(f"🏀 NBA Analyzer — {scrape_date}")
    print(f"{'='*50}\n")

    # Load scraped data
    data = load_nba_data(scrape_date)

    # Load odds if not passed in
    if not odds_data:
        odds_data = load_nba_odds(scrape_date)
        print(f"   📂 Loaded nba_odds ({len(odds_data.get('games', []))} games)")

    # Format odds for prompt
    odds_text = format_nba_odds_for_prompt(odds_data)

    # Build prompt — pass odds_data so games list is available
    prompt = build_nba_prompt(data, odds_text, scrape_date, odds_data)

    # Call Claude
    print("\n🤖 Claude Haiku analyzing NBA slate...")
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text
    print(f"✅ Claude responded ({len(response_text)} chars)")
    print(f"💰 Tokens: {message.usage.input_tokens} in / {message.usage.output_tokens} out")

    # Strip markdown fences if present
    clean = response_text.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
    clean = clean.strip()

    # Parse JSON
    try:
        picks_data = json.loads(clean)
        print("✅ JSON parsed successfully")
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        print(f"Raw response: {response_text[:500]}")
        return None

    # Print summary
    print(f"\n🎯 BEST BET: {picks_data.get('best_bet', 'N/A')}")
    print(f"📋 {picks_data.get('slate_summary', '')}")

    categories = [
        ('points_picks',   '🏀 POINTS'),
        ('rebounds_picks', '💪 REBOUNDS'),
        ('assists_picks',  '🎯 ASSISTS'),
        ('threes_picks',   '3️⃣  THREES'),
        ('combo_picks',    '📊 COMBO'),
        ('game_picks',     '💰 GAME PICKS'),
    ]

    total_picks = 0
    for key, label in categories:
        picks = picks_data.get(key, [])
        total_picks += len(picks)
        if picks:
            print(f"\n{'='*50}")
            print(f"{label} ({len(picks)} picks)")
            print(f"{'='*50}")
            for i, pick in enumerate(picks, 1):
                if key == 'game_picks':
                    print(f"\n  #{i} [{pick.get('confidence')}] "
                          f"{pick.get('pick')} — {pick.get('pick_type')}")
                    print(f"     📅 {pick.get('game')}")
                    print(f"     📖 {pick.get('best_book')} | {pick.get('line')}")
                    print(f"     📝 {pick.get('reasoning', '')[:120]}...")
                else:
                    ou = pick.get('over_under', 'OVER')
                    line = pick.get('prop_line', '')
                    prop_type = pick.get('prop_type', '')
                    label_extra = f" {prop_type}" if prop_type else ""
                    print(f"\n  #{i} [{pick.get('confidence')}] "
                          f"{pick.get('player_name')} — {ou} {line}{label_extra}")
                    print(f"     📅 {pick.get('team')} vs {pick.get('opponent')}")
                    print(f"     📖 {pick.get('best_book')} | {pick.get('best_odds')}")
                    print(f"     📊 Avg: {pick.get('season_avg')} | "
                          f"L5: {pick.get('l5_avg')} | "
                          f"Hit%: {pick.get('hit_rate_season')} | "
                          f"Def: {pick.get('def_rank_vs_pos')}")
                    print(f"     📝 {pick.get('reasoning', '')[:120]}...")

    # Print parlay
    parlay = picks_data.get('best_parlay', {})
    if parlay:
        print(f"\n{'='*50}")
        print(f"🎰 BEST PARLAY")
        print(f"{'='*50}")
        for leg in parlay.get('legs', []):
            print(f"  + {leg}")
        print(f"  Est. Odds: {parlay.get('estimated_odds')}")
        print(f"  📝 {parlay.get('reasoning', '')[:150]}")

    print(f"\n📊 Total NBA picks: {total_picks}")

    # Save picks
    output_file = f"logs/{scrape_date}_nba_picks.json"
    with open(output_file, 'w') as f:
        json.dump(picks_data, f, indent=2)
    print(f"✅ NBA picks saved to {output_file}")

    return picks_data


if __name__ == "__main__":
    run_nba_analyzer()