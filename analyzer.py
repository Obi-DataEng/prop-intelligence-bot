import anthropic
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from news_fetcher import load_news, format_news_for_prompt

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

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

    return f"""You are an elite MLB sports betting analyst. Today is {scrape_date}.

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
- Generate picks in EXACTLY these quantities:
  * hr_picks: EXACTLY 3 picks
  * hits_picks: EXACTLY 3 picks
  * total_bases_picks: EXACTLY 3 picks
  * strikeout_picks: EXACTLY 3 picks
  * game_picks: EXACTLY 4 picks (mix of ML, OU, Spread — at least one of each)
  * laser_picks: EXACTLY 2 picks
- ONLY include picks where you have actual odds data
- For each pick choose the BEST book (highest payout for same line)
- Rank picks within each category by confidence — best pick first

LASER PICKS: 2 players most likely to hit 110+ mph exit velo today. Prioritize elite barrel/hard-hit rates, favorable pitcher matchup, HR-friendly park or warm weather. NOT tied to odds.

REQUIRED OUTPUT FORMAT (JSON only, no markdown, no extra text):
{{
  "laser_picks": [
    {{"rank":1,"player_name":"name","team":"team","opponent":"opp","game":"AWAY @ HOME","game_time":"time","confidence_tier":"Elite | High | Medium","recent_max_ev":"115.3 mph on 4/21","avg_exit_velo":"94.5 mph","barrel_rate":"18%","hard_hit_rate":"55%","pitcher_hard_hit_allowed":"42%","park_factor_hr":1.15,"key_factors":["f1","f2","f3"],"reasoning":"2-3 sentences"}}
  ],
  "hr_picks": [
    {{"rank":1,"player_name":"name","team":"team","opponent":"opp","game":"AWAY @ HOME","game_time":"time","best_book":"FD","fd_odds":"+350","mgm_odds":null,"czs_odds":null,"scr_odds":null,"fd_line":"0.5","confidence_score":85,"confidence_tier":"Elite | High | Medium","key_factors":["f1","f2","f3"],"reasoning":"2-3 sentences","line_shop_note":null}}
  ],
  "hits_picks": [
    {{"rank":1,"player_name":"name","team":"team","opponent":"opp","game":"AWAY @ HOME","game_time":"time","best_book":"FD","fd_odds":"-120","mgm_odds":null,"czs_odds":null,"scr_odds":null,"fd_line":"0.5","over_under_pick":"over","confidence_score":80,"confidence_tier":"Elite | High | Medium","key_factors":["f1","f2","f3"],"reasoning":"2-3 sentences","line_shop_note":null}}
  ],
  "total_bases_picks": [
    {{"rank":1,"player_name":"name","team":"team","opponent":"opp","game":"AWAY @ HOME","game_time":"time","best_book":"FD","fd_odds":"-115","mgm_odds":null,"czs_odds":null,"scr_odds":null,"fd_line":"1.5","over_under_pick":"over","confidence_score":78,"confidence_tier":"Elite | High | Medium","key_factors":["f1","f2","f3"],"reasoning":"2-3 sentences","line_shop_note":null}}
  ],
  "strikeout_picks": [
    {{"rank":1,"player_name":"name","pick_type":"pitcher","team":"team","opponent":"opp","game":"AWAY @ HOME","game_time":"time","best_book":"FD","fd_odds":"-130","mgm_odds":null,"czs_odds":null,"scr_odds":null,"fd_line":"6.5","over_under_pick":"over","confidence_score":75,"confidence_tier":"Elite | High | Medium","key_factors":["f1","f2","f3"],"reasoning":"2-3 sentences","line_shop_note":null}}
  ],
  "game_picks": [
    {{"rank":1,"prop_category":"ML","game":"AWAY @ HOME","game_time":"time","pick":"team name","best_book":"FD","fd_odds":"-140","mgm_odds":null,"czs_odds":null,"scr_odds":null,"fd_line":null,"over_under_pick":null,"confidence_score":72,"confidence_tier":"Elite | High | Medium","key_factors":["f1","f2","f3"],"reasoning":"2-3 sentences","line_shop_note":null}}
  ],
  "best_parlay": {{"legs":["leg1","leg2","leg3"],"reasoning":"why these combine well","estimated_odds":"+450"}},
  "daily_summary": "2-3 sentence overview",
  "best_bet": "single best pick in one sentence"
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

Analyze the NRFI/YRFI research data below and pick the 3 best plays for today.

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
- Pick EXACTLY 3 plays total (NRFI or YRFI)
- NRFI plays: NRFI Score 78+, both pitchers strong NRFI% with active streaks, both teams batting NRFI% above 55%
- YRFI plays: NRFI Score below 50, pitchers with high 1st inning RA, hot-hitting lineups, active YRFI streaks
- Rank by confidence — best play first
- No odds needed — purely data-driven

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

    print("\n🎰 Generating NRFI picks with Claude...")
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
        print(f"   ✅ {len(picks)} NRFI picks generated")
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

def print_picks_section(title, emoji, picks, show_pick_type=False):
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
        label = f"{prop_cat} " if prop_cat else ""
        type_label = f" [{pick_type}]" if show_pick_type and pick_type else ""
        print(f"\n  #{rank} [{tier}] {player}{type_label} — {label}{line_display}")
        print(f"     📅 {game} | {game_time}")
        print(f"     📖 Best: {best_book} | {' | '.join(book_odds) if book_odds else 'No odds found'}")
        if shop: print(f"     💡 {shop}")
        print(f"     📝 {pick.get('reasoning','')[:130]}...")
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
            max_tokens=8000,
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
        print(f"✅ JSON parsed successfully")
        print(f"\n🎯 BEST BET: {picks_data.get('best_bet','N/A')}")
        print(f"📋 {picks_data.get('daily_summary','N/A')}")
        print_picks_section("HOME RUN PICKS", "💣", picks_data.get('hr_picks', []))
        print_picks_section("HITS PICKS", "🎯", picks_data.get('hits_picks', []))
        print_picks_section("TOTAL BASES PICKS", "📊", picks_data.get('total_bases_picks', []))
        print_picks_section("STRIKEOUT PICKS", "🔥", picks_data.get('strikeout_picks', []), show_pick_type=True)
        print_picks_section("GAME PICKS", "💰", picks_data.get('game_picks', []))
        parlay = picks_data.get('best_parlay', {})
        if parlay:
            print(f"\n{'='*50}")
            print(f"🎰 BEST PARLAY")
            print(f"{'='*50}")
            for leg in parlay.get('legs', []):
                print(f"  + {leg}")
            print(f"  Est. Odds: {parlay.get('estimated_odds','N/A')}")
            print(f"  📝 {parlay.get('reasoning','')}")
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