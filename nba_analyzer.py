import anthropic
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from news_fetcher import load_news, format_news_for_prompt

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
        "nba_research"
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
    filepath = f"logs/{scrape_date}_nba_odds.json"
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    print("   ⚠️ No NBA odds file found")
    return {}


def format_nba_odds_for_prompt(odds_data):
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
    if odds_data is None:
        odds_data = {}

    research_data = data.get('nba_research', {})
    research_rows = research_data.get('rows', [])
    research_text = '\n'.join(research_rows[:300])
    news_data = load_news(scrape_date, sport="nba")
    news_text = format_news_for_prompt(news_data)

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

    prompt = f"""You are an expert NBA sports betting analyst focused on HIGH-CONVICTION, HIGH-VALUE plays only. Today is {scrape_date}.

Analyze ALL the data below across every game and every prop category (Points, Rebounds, Assists, Threes, PRA/PR/PA combos, Game ML/Spread/OU).
Your job is to find the 2 single best bets of the entire NBA slate — NOT one per category, just the 2 best overall.

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

=== RECENT NEWS & INJURY CONTEXT ===
{news_text}

SELECTION RULES — READ CAREFULLY:
1. Evaluate ALL prop categories and game bets across the entire NBA slate
2. Select EXACTLY 2 picks total — the 2 best plays you can find anywhere
3. ODDS FILTER (HARD RULE): Only picks where the best available odds are between -130 and +125 (inclusive)
   - ALLOWED examples: -130, -120, -110, -105, +100, +110, +120, +125
   - REJECTED examples: -140, -150, -200, +130, +150, +200
   - If no pick meets the filter, return the 1-2 picks closest to this range and note it
4. Each pick must have MULTIPLE converging edges — defensive matchup + recent form + hit rate + favorable odds
5. Do NOT force picks into categories — find the 2 best plays wherever they are
6. Rank by overall confidence — best pick is rank 1
7. It is playoffs — factor in series context, matchup history, and streak data heavily

WHAT MAKES A GREAT NBA PICK:
- Clear statistical edge vs the line (season avg well above/below, strong L5 trend)
- Bad defensive matchup at the relevant position
- High historical hit rate (65%+) on this prop line
- Odds in the sweet spot (-130 to +125)
- No injury risk (starter confirmed, no load management news)
- Playoff intensity and usage trending up

CRITICAL RULES:
- Only generate picks for games being played on {scrape_date}
- Only include players and games from the TODAY'S ODDS section
- Ignore players who are Out on the injury report
- Always reference the actual prop line from the odds data

REQUIRED OUTPUT FORMAT (JSON only, no markdown, no extra text):
{{
  "top_picks": [
    {{
      "rank": 1,
      "category": "Points | Rebounds | Assists | Threes | PRA | PR | PA | Game ML | Game Spread | Game OU",
      "player_name": "name (or team name for game picks)",
      "pick_type": "player | team",
      "team": "TEAM",
      "opponent": "OPP",
      "game": "AWAY @ HOME",
      "prop_line": 25.5,
      "over_under": "OVER",
      "best_book": "FD",
      "best_odds": -115,
      "fd_odds": -115,
      "mgm_odds": null,
      "czs_odds": null,
      "confidence_tier": "Elite | High | Medium",
      "confidence_score": 88,
      "season_avg": 27.2,
      "l5_avg": 28.1,
      "def_rank_vs_pos": "#24 (Bad)",
      "hit_rate_season": "68%",
      "key_factors": ["factor1", "factor2", "factor3"],
      "reasoning": "2-3 sentences explaining why this is one of the 2 best plays on the NBA slate today",
      "line_shop_note": "note if meaningful odds difference exists, or null"
    }}
  ],
  "slate_summary": "1-2 sentence overview of today's NBA slate and why these 2 picks stand out",
  "best_bet": "The single best NBA pick in one sentence"
}}

Return ONLY valid JSON. No markdown fences, no explanation outside JSON."""

    return prompt


def run_nba_analyzer(scrape_date=None, odds_data=None):
    if not scrape_date:
        scrape_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*50}")
    print(f"🏀 NBA Analyzer — {scrape_date}")
    print(f"{'='*50}\n")

    data = load_nba_data(scrape_date)

    if not odds_data:
        odds_data = load_nba_odds(scrape_date)
        print(f"   📂 Loaded nba_odds ({len(odds_data.get('games', []))} games)")

    odds_text = format_nba_odds_for_prompt(odds_data)
    prompt = build_nba_prompt(data, odds_text, scrape_date, odds_data)

    print("\n🤖 Claude Haiku analyzing NBA slate...")
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text
    print(f"✅ Claude responded ({len(response_text)} chars)")
    print(f"💰 Tokens: {message.usage.input_tokens} in / {message.usage.output_tokens} out")

    clean = response_text.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
    clean = clean.strip()

    try:
        picks_data = json.loads(clean)
        print("✅ JSON parsed successfully")
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        print(f"Raw response: {response_text[:500]}")
        return None

    print(f"\n🎯 BEST BET: {picks_data.get('best_bet', 'N/A')}")
    print(f"📋 {picks_data.get('slate_summary', '')}")

    top_picks = picks_data.get('top_picks', [])
    print(f"\n{'='*50}")
    print(f"⭐ TODAY'S TOP NBA PICKS ({len(top_picks)} picks)")
    print(f"{'='*50}")
    for pick in top_picks:
        tier = pick.get('confidence_tier', 'Medium')
        player = pick.get('player_name', 'N/A')
        cat = pick.get('category', '')
        ou = pick.get('over_under', '')
        line = pick.get('prop_line', '')
        book = pick.get('best_book', '')
        odds = pick.get('best_odds', '')
        print(f"\n  #{pick.get('rank')} [{tier}] {player} — {cat} | {ou} {line}")
        print(f"     📅 {pick.get('game')} &nbsp;|&nbsp; {pick.get('team')} vs {pick.get('opponent')}")
        print(f"     📖 {book} {odds} &nbsp;|&nbsp; Avg: {pick.get('season_avg')} | L5: {pick.get('l5_avg')} | Hit%: {pick.get('hit_rate_season')} | Def: {pick.get('def_rank_vs_pos')}")
        print(f"     📝 {pick.get('reasoning','')[:150]}...")

    print(f"\n📊 Total NBA picks: {len(top_picks)}")

    output_file = f"logs/{scrape_date}_nba_picks.json"
    with open(output_file, 'w') as f:
        json.dump(picks_data, f, indent=2)
    print(f"✅ NBA picks saved to {output_file}")

    return picks_data


if __name__ == "__main__":
    run_nba_analyzer()