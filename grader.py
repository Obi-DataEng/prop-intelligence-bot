import requests
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from difflib import SequenceMatcher
import unicodedata

load_dotenv()

MLB_STATS_URL = "https://statsapi.mlb.com/api/v1"
DB_PATH = "data/mlb_picks.db"

# ─────────────────────────────────────────────
# NAME MATCHING
# ─────────────────────────────────────────────

def normalize_name(name):
    if not name:
        return ""
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.lower().strip()
    for suffix in [' jr.', ' jr', ' sr.', ' sr', ' ii', ' iii', ' iv']:
        name = name.replace(suffix, '')
    return name.strip()

def fuzzy_match_player(pick_name, api_players, threshold=0.85):
    pick_normalized = normalize_name(pick_name)
    best_match = None
    best_score = 0
    for api_name in api_players:
        api_normalized = normalize_name(api_name)
        score = SequenceMatcher(None, pick_normalized, api_normalized).ratio()
        if score > best_score:
            best_score = score
            best_match = api_name
    if best_score >= threshold:
        return best_match, best_score
    return None, 0

# ─────────────────────────────────────────────
# RECORD-ONLY RESULT CALCULATION
# ─────────────────────────────────────────────

def grade_result(actual, line, over_under, did_play, odds=None, bet=None):
    if not did_play:
        return 'push', 0
    try:
        actual = float(actual)
        line = float(line)
    except:
        return 'pending', 0
    if actual == line:
        return 'push', 0
    ou = over_under.lower() if over_under else 'over'
    if ou == 'over':
        return ('win', 0) if actual > line else ('loss', 0)
    else:
        return ('win', 0) if actual < line else ('loss', 0)

# ─────────────────────────────────────────────
# MLB STATS API
# ─────────────────────────────────────────────

def get_mlb_boxscores(date_str):
    print(f"\n   🔍 Fetching MLB box scores for {date_str}...")
    try:
        params = {"sportId": 1, "date": date_str, "hydrate": "boxscore"}
        r = requests.get(f"{MLB_STATS_URL}/schedule", params=params, timeout=30)
        if r.status_code != 200:
            print(f"   ❌ MLB schedule error: {r.status_code}")
            return {}, []

        data = r.json()
        dates = data.get('dates', [])
        if not dates:
            print(f"   ⚠️ No MLB games found for {date_str}")
            return {}, []

        player_stats = {}
        game_results = []

        for date in dates:
            for game in date.get('games', []):
                if game.get('status', {}).get('abstractGameState', '') != 'Final':
                    continue
                game_pk = game.get('gamePk')
                home_team = game.get('teams', {}).get('home', {}).get('team', {}).get('name', '')
                away_team = game.get('teams', {}).get('away', {}).get('team', {}).get('name', '')
                home_score = game.get('teams', {}).get('home', {}).get('score', 0)
                away_score = game.get('teams', {}).get('away', {}).get('score', 0)
                game_results.append({'home_team': home_team, 'away_team': away_team, 'home_score': home_score, 'away_score': away_score, 'total': home_score + away_score})

                box_r = requests.get(f"{MLB_STATS_URL}/game/{game_pk}/boxscore", timeout=30)
                if box_r.status_code != 200:
                    continue
                box = box_r.json()
                for side in ['home', 'away']:
                    players = box.get('teams', {}).get(side, {}).get('players', {})
                    for pid, pdata in players.items():
                        name = pdata.get('person', {}).get('fullName', '')
                        batting = pdata.get('stats', {}).get('batting', {})
                        pitching = pdata.get('stats', {}).get('pitching', {})
                        pa = batting.get('plateAppearances', 0)
                        ip = pitching.get('inningsPitched', '0')
                        did_play = pa > 0 or float(ip or 0) > 0
                        player_stats[name] = {
                            'did_play': did_play,
                            'hits': batting.get('hits', 0),
                            'home_runs': batting.get('homeRuns', 0),
                            'total_bases': batting.get('totalBases', 0),
                            'strikeouts_batter': batting.get('strikeOuts', 0),
                            'strikeouts_pitcher': pitching.get('strikeOuts', 0),
                            'at_bats': batting.get('atBats', 0),
                            'plate_appearances': pa,
                            'innings_pitched': float(ip or 0)
                        }

        print(f"   ✅ {len(player_stats)} MLB players found across {len(game_results)} games")
        return player_stats, game_results
    except Exception as e:
        print(f"   ❌ MLB box score error: {e}")
        return {}, []

# ─────────────────────────────────────────────
# FIRST INNING RESULTS (for NRFI grading)
# ─────────────────────────────────────────────

def get_first_inning_results(date_str):
    results = []
    try:
        r = requests.get(f"{MLB_STATS_URL}/schedule", params={"sportId": 1, "date": date_str}, timeout=30)
        if r.status_code != 200:
            return results
        for date in r.json().get('dates', []):
            for game in date.get('games', []):
                if game.get('status', {}).get('abstractGameState', '') != 'Final':
                    continue
                game_pk = game.get('gamePk')
                home_team = game.get('teams', {}).get('home', {}).get('team', {}).get('name', '')
                away_team = game.get('teams', {}).get('away', {}).get('team', {}).get('name', '')
                ls_r = requests.get(f"{MLB_STATS_URL}/game/{game_pk}/linescore", timeout=30)
                if ls_r.status_code != 200:
                    continue
                innings = ls_r.json().get('innings', [])
                if innings:
                    first = innings[0]
                    home_r1 = first.get('home', {}).get('runs', 0) or 0
                    away_r1 = first.get('away', {}).get('runs', 0) or 0
                    results.append({'home_team': home_team, 'away_team': away_team, 'home_runs_1': home_r1, 'away_runs_1': away_r1, 'runs_first_inning': home_r1 + away_r1})
        print(f"   ✅ First inning data fetched for {len(results)} games")
        return results
    except Exception as e:
        print(f"   ❌ First inning fetch error: {e}")
        return []

# ─────────────────────────────────────────────
# NBA ESPN API
# ─────────────────────────────────────────────

def get_nba_boxscores(date_str):
    print(f"\n   🔍 Fetching NBA box scores for {date_str}...")
    try:
        date_compact = date_str.replace('-', '')
        r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_compact}", timeout=30)
        if r.status_code != 200:
            print(f"   ❌ ESPN scoreboard error: {r.status_code}")
            return {}

        events = r.json().get('events', [])
        finished_events = [e for e in events if e.get('status', {}).get('type', {}).get('completed', False)]
        if not finished_events:
            print(f"   ⚠️ No completed NBA games found for {date_str}")
            return {}

        print(f"   📋 Found {len(finished_events)} completed NBA games, fetching box scores...")
        player_stats = {}

        for event in finished_events:
            game_id = event.get('id')
            if not game_id:
                continue
            box_r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={game_id}", timeout=30)
            if box_r.status_code != 200:
                continue
            boxscore = box_r.json().get('boxscore', {})
            for team in boxscore.get('players', []):
                statistics = team.get('statistics', [])
                if not statistics:
                    continue
                stat_block = statistics[0]
                labels = stat_block.get('labels', [])
                for athlete in stat_block.get('athletes', []):
                    name = athlete.get('athlete', {}).get('displayName', '')
                    stats_list = athlete.get('stats', [])
                    if not stats_list or not name:
                        continue
                    stat_map = dict(zip(labels, stats_list))
                    min_str = stat_map.get('MIN', '0') or '0'
                    try:
                        mins = int(min_str.split(':')[0]) if ':' in str(min_str) else int(float(min_str))
                    except:
                        mins = 0

                    def safe_int(val):
                        try:
                            return int(val) if val not in (None, '--', '') else 0
                        except:
                            return 0

                    pts = safe_int(stat_map.get('PTS', 0))
                    reb = safe_int(stat_map.get('REB', 0))
                    ast = safe_int(stat_map.get('AST', 0))
                    stl = safe_int(stat_map.get('STL', 0))
                    blk = safe_int(stat_map.get('BLK', 0))
                    fg3_raw = stat_map.get('3PT', '0-0') or '0-0'
                    try:
                        fg3m = int(str(fg3_raw).split('-')[0])
                    except:
                        fg3m = 0
                    player_stats[name] = {
                        'did_play': mins > 0,
                        'pts': pts, 'reb': reb, 'ast': ast,
                        'fg3m': fg3m, 'stl': stl, 'blk': blk,
                        'pra': pts + reb + ast, 'pr': pts + reb, 'pa': pts + ast,
                        'min': mins
                    }

        print(f"   ✅ {len(player_stats)} NBA players found across {len(finished_events)} games")
        return player_stats
    except Exception as e:
        print(f"   ❌ NBA box score error: {e}")
        return {}

# ─────────────────────────────────────────────
# GAME PICK GRADING
# ─────────────────────────────────────────────

def grade_game_pick(pick, game_results):
    game_str = pick.get('game', '')
    prop = pick.get('prop_category', '')
    pick_team = pick.get('pick', '')
    fd_line = pick.get('fd_line')
    ou_pick = (pick.get('over_under_pick') or '').lower()

    for game in game_results:
        home = game['home_team']
        away = game['away_team']
        if not (home in game_str or away in game_str or any(t in game_str for t in [home[:6], away[:6]])):
            continue
        home_score = game['home_score']
        away_score = game['away_score']
        total = game['total']
        if prop == 'ML':
            winner = home if home_score > away_score else away
            return ('win' if pick_team in winner else 'loss', 0)
        elif prop == 'OU':
            try:
                line = float(fd_line)
            except:
                return 'pending', 0
            if total == line:
                return 'push', 0
            result = 'win' if (ou_pick == 'over' and total > line) or (ou_pick != 'over' and total < line) else 'loss'
            return result, 0
        elif prop == 'Spread':
            try:
                line = float(fd_line)
            except:
                return 'pending', 0
            margin = (home_score - away_score) if pick_team in home else (away_score - home_score)
            if margin + line == 0:
                return 'push', 0
            result = 'win' if margin + line > 0 else 'loss'
            return result, 0
    return 'pending', 0

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS pick_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pick_date TEXT, graded_date TEXT, sport TEXT, category TEXT,
        player_name TEXT, game TEXT, over_under TEXT, line REAL,
        odds TEXT, best_book TEXT, result TEXT, actual_value REAL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS parlay_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pick_date TEXT, graded_date TEXT, sport TEXT, legs TEXT,
        estimated_odds TEXT, result TEXT)''')
    conn.commit()
    conn.close()

def already_graded(pick_date, sport):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM pick_results WHERE pick_date = ? AND sport = ?', (pick_date, sport))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except:
        return False

def already_graded_category(pick_date, sport, category):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM pick_results WHERE pick_date = ? AND sport = ? AND category = ?', (pick_date, sport, category))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except:
        return False

def save_pick_result(pick_date, graded_date, sport, category, player_name, game, over_under, line, odds, best_book, result, actual_value, profit_loss):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO pick_results
        (pick_date, graded_date, sport, category, player_name, game, over_under, line, odds, best_book, result, actual_value)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (pick_date, graded_date, sport, category, player_name, game, over_under, line, odds, best_book, result, actual_value))
    conn.commit()
    conn.close()

def save_parlay_result(pick_date, graded_date, sport, legs, estimated_odds, result, profit_loss):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO parlay_results (pick_date, graded_date, sport, legs, estimated_odds, result)
        VALUES (?, ?, ?, ?, ?, ?)''',
        (pick_date, graded_date, sport, json.dumps(legs), estimated_odds, result))
    conn.commit()
    conn.close()

def get_cumulative_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    stats = {}
    try:
        cursor.execute('''SELECT sport, category,
            SUM(CASE WHEN result='win' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='push' THEN 1 ELSE 0 END)
            FROM pick_results WHERE result IN ('win','loss','push')
            GROUP BY sport, category ORDER BY sport, category''')
        for row in cursor.fetchall():
            sport, cat, wins, losses, pushes = row
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            stats[f"{sport} - {cat}"] = {
                'sport': sport, 'category': cat,
                'wins': wins or 0, 'losses': losses or 0, 'pushes': pushes or 0,
                'win_rate': round(win_rate, 1)
            }
        cursor.execute('''SELECT sport,
            SUM(CASE WHEN result='win' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END)
            FROM parlay_results WHERE result IN ('win','loss') GROUP BY sport''')
        for row in cursor.fetchall():
            sport, wins, losses = row
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            stats[f"{sport} - Parlay"] = {
                'sport': sport, 'category': 'Parlay',
                'wins': wins or 0, 'losses': losses or 0, 'pushes': 0,
                'win_rate': round(win_rate, 1)
            }
        cursor.execute('''SELECT
            SUM(CASE WHEN result='win' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='push' THEN 1 ELSE 0 END)
            FROM (
                SELECT result FROM pick_results WHERE result IN ('win','loss','push')
                UNION ALL
                SELECT result FROM parlay_results WHERE result IN ('win','loss')
            )''')
        row = cursor.fetchone()
        if row:
            wins, losses, pushes = row
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            stats['OVERALL'] = {
                'wins': wins or 0, 'losses': losses or 0, 'pushes': pushes or 0,
                'win_rate': round(win_rate, 1)
            }
    except Exception as e:
        print(f"   ❌ Stats error: {e}")
        import traceback; traceback.print_exc()
    conn.close()
    return stats

def get_daily_summary_from_db(pick_date):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    summary = {}
    try:
        cursor.execute('''SELECT sport, category,
            SUM(CASE WHEN result='win' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='push' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='pending' THEN 1 ELSE 0 END)
            FROM pick_results WHERE pick_date = ? GROUP BY sport, category''', (pick_date,))
        for row in cursor.fetchall():
            sport, cat, wins, losses, pushes, pending = row
            summary[f"{sport} - {cat}"] = {
                'wins': wins or 0, 'losses': losses or 0, 'pushes': pushes or 0,
                'pending': pending or 0
            }
    except Exception as e:
        print(f"   ❌ Daily summary error: {e}")
    conn.close()
    return summary

# ─────────────────────────────────────────────
# MLB GRADER
# ─────────────────────────────────────────────

def grade_mlb_picks(picks_data, player_stats, game_results, pick_date, graded_date):
    summary = {}
    api_players = list(player_stats.keys())
    mlb_categories = {
        'hr_picks':          ('HR',   'home_runs',  None),
        'hits_picks':        ('Hits', 'hits',        'over_under_pick'),
        'total_bases_picks': ('TB',   'total_bases', 'over_under_pick'),
        'strikeout_picks':   ('K',    None,          'over_under_pick'),
    }
    for key, (cat, stat_field, ou_field) in mlb_categories.items():
        picks = picks_data.get(key, [])
        wins = losses = pushes = pending = 0
        profit = 0
        for pick in picks:
            player_name = pick.get('player_name', '')
            pick_type = pick.get('pick_type', 'batter')
            line = pick.get('fd_line')
            ou = (pick.get(ou_field) or 'over') if ou_field else 'over'
            odds = pick.get('fd_odds') or pick.get('czs_odds') or pick.get('mgm_odds')
            if cat == 'HR':
                ou = 'over'; line = 0.5
            if cat == 'K':
                stat_field = 'strikeouts_pitcher' if 'pitcher' in str(pick_type).lower() else 'strikeouts_batter'
            matched_name, score = fuzzy_match_player(player_name, api_players)
            if not matched_name:
                result, pl = 'pending', 0; actual_value = None; pending += 1
            else:
                pstats = player_stats[matched_name]
                did_play = pstats['did_play']
                actual_value = pstats.get(stat_field, 0)
                try:
                    result, pl = grade_result(actual_value, line, ou, did_play, odds)
                except:
                    result, pl = 'pending', 0; actual_value = None
                if result == 'win': wins += 1
                elif result == 'loss': losses += 1
                elif result == 'push': pushes += 1
                else: pending += 1
                profit += pl
            save_pick_result(pick_date, graded_date, 'MLB', cat, player_name, pick.get('game',''), ou, line, odds, pick.get('best_book',''), result, actual_value, pl)
        summary[cat] = {'wins': wins, 'losses': losses, 'pushes': pushes, 'pending': pending, 'profit': round(profit, 2)}

    game_picks = picks_data.get('game_picks', [])
    ml_wins = ml_losses = ml_pushes = spread_wins = spread_losses = spread_pushes = ou_wins = ou_losses = ou_pushes = 0
    ml_profit = spread_profit = ou_profit = 0
    for pick in game_picks:
        prop = pick.get('prop_category', 'ML')
        result, pl = grade_game_pick(pick, game_results)
        save_pick_result(pick_date, graded_date, 'MLB', f"Game {prop}", pick.get('pick',''), pick.get('game',''), pick.get('over_under_pick',''), pick.get('fd_line'), pick.get('fd_odds'), pick.get('best_book',''), result, None, pl)
        if prop == 'ML':
            if result == 'win': ml_wins += 1; ml_profit += pl
            elif result == 'loss': ml_losses += 1; ml_profit += pl
            elif result == 'push': ml_pushes += 1
        elif prop == 'Spread':
            if result == 'win': spread_wins += 1; spread_profit += pl
            elif result == 'loss': spread_losses += 1; spread_profit += pl
            elif result == 'push': spread_pushes += 1
        elif prop == 'OU':
            if result == 'win': ou_wins += 1; ou_profit += pl
            elif result == 'loss': ou_losses += 1; ou_profit += pl
            elif result == 'push': ou_pushes += 1

    summary['Game ML']     = {'wins': ml_wins,     'losses': ml_losses,     'pushes': ml_pushes,     'pending': 0, 'profit': round(ml_profit, 2)}
    summary['Game Spread'] = {'wins': spread_wins, 'losses': spread_losses, 'pushes': spread_pushes, 'pending': 0, 'profit': round(spread_profit, 2)}
    summary['Game OU']     = {'wins': ou_wins,     'losses': ou_losses,     'pushes': ou_pushes,     'pending': 0, 'profit': round(ou_profit, 2)}
    return summary

# ─────────────────────────────────────────────
# NRFI GRADER
# ─────────────────────────────────────────────

def grade_nrfi_picks(nrfi_picks, pick_date, graded_date):
    # FIX 1: guard against empty picks — all keys defined, no undefined vars
    if not nrfi_picks:
        return {'wins': 0, 'losses': 0, 'pushes': 0, 'pending': 0, 'profit': 0}

    print(f"\n🎰 Grading NRFI picks for {pick_date}...")

    if already_graded_category(pick_date, 'MLB', 'NRFI'):
        print(f"   ⚠️ NRFI picks for {pick_date} already graded — skipping")
        summary = get_daily_summary_from_db(pick_date)
        return summary.get('MLB - NRFI', {'wins': 0, 'losses': 0, 'pushes': 0, 'pending': 0, 'profit': 0})

    first_inning = get_first_inning_results(pick_date)
    wins = losses = pending = 0

    for pick in nrfi_picks:
        game = pick.get('game', '')
        bet = pick.get('pick', 'NRFI').upper()
        result = 'pending'
        runs_str = ''

        for fi in first_inning:
            home = fi.get('home_team', '')
            away = fi.get('away_team', '')
            if (home in game or away in game or any(t in game for t in [home[:6], away[:6], home.split()[-1], away.split()[-1]])):
                runs_first = fi.get('runs_first_inning')
                if runs_first is not None:
                    result = ('win' if runs_first == 0 else 'loss') if bet == 'NRFI' else ('win' if runs_first > 0 else 'loss')
                    runs_str = f"({runs_first} runs 1st)"
                break

        if result == 'win': wins += 1
        elif result == 'loss': losses += 1
        else: pending += 1

        pitchers = f"{pick.get('away_pitcher','')} / {pick.get('home_pitcher','')}"
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO pick_results
            (pick_date, graded_date, sport, category, player_name, game, over_under, line, odds, best_book, result, actual_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (pick_date, graded_date, 'MLB', 'NRFI', pitchers, game, bet, None, None, 'N/A', result, None))
        conn.commit()
        conn.close()
        print(f"   {result.upper():7} — {bet} {game} {runs_str}")

    print(f"   📊 NRFI: {wins}W - {losses}L - {pending} pending")
    # FIX 2: include 'pushes' key in return dict
    return {'wins': wins, 'losses': losses, 'pushes': 0, 'pending': pending, 'profit': 0}

# ─────────────────────────────────────────────
# NBA GRADER
# ─────────────────────────────────────────────

def grade_nba_picks(nba_picks_data, nba_player_stats, pick_date, graded_date):
    summary = {}
    api_players = list(nba_player_stats.keys())
    nba_categories = {
        'points_picks':   ('Points',   'pts'),
        'rebounds_picks': ('Rebounds', 'reb'),
        'assists_picks':  ('Assists',  'ast'),
        'threes_picks':   ('Threes',   'fg3m'),
    }
    for key, (cat, stat_field) in nba_categories.items():
        picks = nba_picks_data.get(key, [])
        wins = losses = pushes = pending = 0; profit = 0
        for pick in picks:
            player_name = pick.get('player_name', '')
            line = pick.get('prop_line')
            ou = pick.get('over_under', 'OVER')
            odds = pick.get('best_odds')
            matched_name, score = fuzzy_match_player(player_name, api_players)
            if not matched_name:
                result, pl = 'pending', 0; actual_value = None; pending += 1
            else:
                pstats = nba_player_stats[matched_name]
                actual_value = pstats.get(stat_field, 0)
                result, pl = grade_result(actual_value, line, ou, pstats['did_play'], odds)
                if result == 'win': wins += 1
                elif result == 'loss': losses += 1
                elif result == 'push': pushes += 1
                else: pending += 1
                profit += pl
            save_pick_result(pick_date, graded_date, 'NBA', cat, player_name, pick.get('team','') + ' vs ' + pick.get('opponent',''), ou, line, odds, pick.get('best_book',''), result, actual_value, pl)
        summary[cat] = {'wins': wins, 'losses': losses, 'pushes': pushes, 'pending': pending, 'profit': round(profit, 2)}

    combo_stat_map = {'PRA': 'pra', 'PR': 'pr', 'PA': 'pa', 'pts': 'pts', 'reb': 'reb', 'ast': 'ast'}
    wins = losses = pushes = pending = 0; profit = 0
    for pick in nba_picks_data.get('combo_picks', []):
        player_name = pick.get('player_name', '')
        line = pick.get('prop_line'); ou = pick.get('over_under', 'OVER'); odds = pick.get('best_odds')
        stat_field = combo_stat_map.get(pick.get('prop_type', 'PRA').upper(), 'pra')
        matched_name, score = fuzzy_match_player(player_name, api_players)
        if not matched_name:
            result, pl = 'pending', 0; actual_value = None; pending += 1
        else:
            pstats = nba_player_stats[matched_name]
            actual_value = pstats.get(stat_field, 0)
            result, pl = grade_result(actual_value, line, ou, pstats['did_play'], odds)
            if result == 'win': wins += 1
            elif result == 'loss': losses += 1
            elif result == 'push': pushes += 1
            else: pending += 1
            profit += pl
        save_pick_result(pick_date, graded_date, 'NBA', 'Combo', player_name, pick.get('team','') + ' vs ' + pick.get('opponent',''), ou, line, odds, pick.get('best_book',''), result, actual_value, pl)
    summary['Combo'] = {'wins': wins, 'losses': losses, 'pushes': pushes, 'pending': pending, 'profit': round(profit, 2)}

    pending = 0
    for pick in nba_picks_data.get('game_picks', []):
        pending += 1
        save_pick_result(pick_date, graded_date, 'NBA', 'Game', pick.get('pick',''), pick.get('game',''), 'over', None, pick.get('line'), pick.get('best_book',''), 'pending', None, 0)
    summary['Game'] = {'wins': 0, 'losses': 0, 'pushes': 0, 'pending': pending, 'profit': 0}
    return summary

# ─────────────────────────────────────────────
# ESPN MULTI-SPORT RESULTS (CFB / NFL / WNBA)
# ─────────────────────────────────────────────

ESPN_SPORT_PATHS = {
    'CFB': 'football/college-football',
    'NFL': 'football/nfl',
    'WNBA': 'basketball/wnba',
}


def normalize_team(name):
    """Normalize team names/abbreviations for conservative game matching."""
    value = normalize_name(str(name or ''))
    value = re.sub(r'[^a-z0-9 ]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def safe_stat_number(value):
    """Convert ESPN values such as 17, 17.5, 3-5 or 3/5 to a numeric value."""
    if value in (None, '', '--'):
        return 0.0
    text = str(value).strip()
    if re.fullmatch(r'-?\d+(?:\.\d+)?', text):
        return float(text)
    # Made-attempt values: the first number is the made count.
    match = re.match(r'^(-?\d+(?:\.\d+)?)\s*[-/]\s*\d+', text)
    if match:
        return float(match.group(1))
    match = re.search(r'-?\d+(?:\.\d+)?', text)
    return float(match.group()) if match else 0.0


def stat_key(value):
    value = normalize_name(str(value or ''))
    return re.sub(r'[^a-z0-9]+', '_', value).strip('_')


def get_espn_results(sport, date_str):
    """Return completed ESPN game results and per-player box-score stats."""
    sport = sport.upper()
    path = ESPN_SPORT_PATHS[sport]
    date_compact = date_str.replace('-', '')
    scoreboard_url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
    summary_url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/summary"
    print(f"\n   🔍 Fetching {sport} results for {date_str}...")

    try:
        response = requests.get(
            scoreboard_url,
            params={'dates': date_compact, 'limit': 1000},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"   ❌ {sport} scoreboard error: {error}")
        return {}, []

    players = {}
    games = []
    completed_events = [
        event for event in response.json().get('events', [])
        if event.get('status', {}).get('type', {}).get('completed', False)
    ]

    for event in completed_events:
        competition = (event.get('competitions') or [{}])[0]
        competitors = competition.get('competitors', [])
        home_entry = next((team for team in competitors if team.get('homeAway') == 'home'), {})
        away_entry = next((team for team in competitors if team.get('homeAway') == 'away'), {})

        def team_identity(entry):
            team = entry.get('team', {})
            return {
                'name': team.get('displayName') or team.get('shortDisplayName') or '',
                'short_name': team.get('shortDisplayName') or '',
                'abbreviation': team.get('abbreviation') or '',
            }

        home_identity = team_identity(home_entry)
        away_identity = team_identity(away_entry)
        try:
            home_score = float(home_entry.get('score', 0) or 0)
            away_score = float(away_entry.get('score', 0) or 0)
        except (TypeError, ValueError):
            continue

        games.append({
            'event_id': event.get('id'),
            'home_team': home_identity['name'],
            'home_short_name': home_identity['short_name'],
            'home_abbreviation': home_identity['abbreviation'],
            'away_team': away_identity['name'],
            'away_short_name': away_identity['short_name'],
            'away_abbreviation': away_identity['abbreviation'],
            'home_score': home_score,
            'away_score': away_score,
            'total': home_score + away_score,
        })

        event_id = event.get('id')
        if not event_id:
            continue
        try:
            box_response = requests.get(summary_url, params={'event': event_id}, timeout=30)
            box_response.raise_for_status()
            boxscore = box_response.json().get('boxscore', {})
        except requests.RequestException as error:
            print(f"   ⚠️ Could not fetch {sport} box score {event_id}: {error}")
            continue

        for team_block in boxscore.get('players', []):
            team_info = team_block.get('team', {})
            team_name = team_info.get('displayName') or team_info.get('shortDisplayName') or ''
            team_abbr = team_info.get('abbreviation') or ''
            for stat_group in team_block.get('statistics', []):
                group_name = stat_key(
                    stat_group.get('name')
                    or stat_group.get('displayName')
                    or stat_group.get('type')
                    or 'general'
                )
                labels = stat_group.get('labels') or stat_group.get('names') or []
                for athlete_row in stat_group.get('athletes', []):
                    athlete = athlete_row.get('athlete', {})
                    player_name = athlete.get('displayName') or athlete.get('fullName') or ''
                    if not player_name:
                        continue
                    player_key = normalize_name(player_name)
                    record = players.setdefault(player_key, {
                        'name': player_name,
                        'team': team_name,
                        'team_abbreviation': team_abbr,
                        'did_play': False,
                        'stats': {},
                    })
                    raw_stats = athlete_row.get('stats', [])
                    if raw_stats:
                        record['did_play'] = True
                    for label, value in zip(labels, raw_stats):
                        label_key = stat_key(label)
                        number = safe_stat_number(value)
                        record['stats'][f'{group_name}_{label_key}'] = number
                        # Keep unprefixed basketball labels where they are unambiguous.
                        if sport == 'WNBA':
                            record['stats'][label_key] = number

    print(f"   ✅ {len(games)} completed {sport} games | {len(players)} players")
    return players, games


def team_aliases(game, side):
    return {
        normalize_team(game.get(f'{side}_team')),
        normalize_team(game.get(f'{side}_short_name')),
        normalize_team(game.get(f'{side}_abbreviation')),
    } - {''}


def find_espn_game(pick, game_results):
    """Match a saved pick to exactly one completed ESPN event."""
    game_text = normalize_team(pick.get('game') or '')
    pick_team = normalize_team(pick.get('team') or pick.get('pick') or '')
    matches = []
    for game in game_results:
        home_aliases = team_aliases(game, 'home')
        away_aliases = team_aliases(game, 'away')
        all_aliases = home_aliases | away_aliases
        game_hits = sum(1 for alias in all_aliases if len(alias) >= 2 and re.search(rf'\b{re.escape(alias)}\b', game_text))
        team_hit = any(
            alias == pick_team or (len(alias) >= 4 and alias in pick_team)
            for alias in all_aliases
        )
        if game_hits >= 2 or (game_hits >= 1 and team_hit):
            matches.append(game)
    return matches[0] if len(matches) == 1 else None


def selected_side(pick, game):
    value = normalize_team(pick.get('team') or pick.get('pick') or pick.get('selection') or '')
    home_match = any(alias == value or (len(alias) >= 4 and alias in value) for alias in team_aliases(game, 'home'))
    away_match = any(alias == value or (len(alias) >= 4 and alias in value) for alias in team_aliases(game, 'away'))
    if home_match and not away_match:
        return 'home'
    if away_match and not home_match:
        return 'away'
    return None


def canonical_pick_type(pick):
    value = stat_key(pick.get('pick_type') or pick.get('prop_category') or '')
    if value in {'ml', 'money_line', 'moneyline'}:
        return 'moneyline'
    if value in {'ou', 'o_u', 'total', 'game_total', 'game_ou'}:
        return 'game_total'
    if value == 'spread':
        return 'spread'
    if value in {'player_prop', 'prop'}:
        return 'player_prop'
    selection = normalize_team(pick.get('selection') or pick.get('pick') or '')
    if 'moneyline' in selection:
        return 'moneyline'
    if selection.startswith('over ') or selection.startswith('under '):
        return 'game_total'
    return value


def grade_espn_game_pick(pick, game_results):
    game = find_espn_game(pick, game_results)
    if not game:
        return 'pending', None

    pick_type = canonical_pick_type(pick)
    home_score = game['home_score']
    away_score = game['away_score']

    if pick_type == 'moneyline':
        side = selected_side(pick, game)
        if not side or home_score == away_score:
            return 'pending', None
        winner = 'home' if home_score > away_score else 'away'
        return ('win' if side == winner else 'loss'), home_score - away_score

    if pick_type == 'spread':
        side = selected_side(pick, game)
        try:
            line = float(pick.get('line') if pick.get('line') is not None else pick.get('fd_line'))
        except (TypeError, ValueError):
            return 'pending', None
        if not side:
            return 'pending', None
        margin = home_score - away_score if side == 'home' else away_score - home_score
        adjusted = margin + line
        if adjusted == 0:
            return 'push', margin
        return ('win' if adjusted > 0 else 'loss'), margin

    if pick_type == 'game_total':
        try:
            line = float(pick.get('line') if pick.get('line') is not None else pick.get('fd_line'))
        except (TypeError, ValueError):
            return 'pending', None
        direction = str(pick.get('over_under') or pick.get('over_under_pick') or '').lower()
        if not direction:
            selection = str(pick.get('selection') or pick.get('pick') or '').lower()
            direction = 'over' if selection.startswith('over') else 'under' if selection.startswith('under') else ''
        if direction not in {'over', 'under'}:
            return 'pending', game['total']
        result, _ = grade_result(game['total'], line, direction, True)
        return result, game['total']

    return 'pending', None


def first_existing_stat(stats, candidates):
    for candidate in candidates:
        if candidate in stats:
            return stats[candidate]
    return None


def prop_actual_value(sport, market, stats):
    """Map analyzer/PropFinder market labels to ESPN box-score fields."""
    market_key = stat_key(market)
    if sport == 'WNBA':
        mapping = {
            'points': ['pts', 'points_pts'],
            'pts': ['pts'],
            'rebounds': ['reb', 'rebounds_reb'],
            'reb': ['reb'],
            'assists': ['ast', 'assists_ast'],
            'ast': ['ast'],
            'three_pointers_made': ['3pt', '3pm', 'fg3m'],
            'threes': ['3pt', '3pm', 'fg3m'],
            'steals': ['stl'],
            'blocks': ['blk'],
            'turnovers': ['to'],
        }
        if market_key in {'pra', 'points_rebounds_assists'}:
            values = [first_existing_stat(stats, mapping[key]) for key in ('points', 'rebounds', 'assists')]
            return sum(values) if all(value is not None for value in values) else None
        if market_key in {'pr', 'points_rebounds'}:
            values = [first_existing_stat(stats, mapping[key]) for key in ('points', 'rebounds')]
            return sum(values) if all(value is not None for value in values) else None
        if market_key in {'pa', 'points_assists'}:
            values = [first_existing_stat(stats, mapping[key]) for key in ('points', 'assists')]
            return sum(values) if all(value is not None for value in values) else None
        return first_existing_stat(stats, mapping.get(market_key, []))

    mapping = {
        'passing_yds': ['passing_yds', 'passing_yards'],
        'passing_yards': ['passing_yds', 'passing_yards'],
        'passing_tds': ['passing_td', 'passing_tds'],
        'passing_touchdowns': ['passing_td', 'passing_tds'],
        'interceptions': ['passing_int', 'passing_interceptions'],
        'rushing_yds': ['rushing_yds', 'rushing_yards'],
        'rushing_yards': ['rushing_yds', 'rushing_yards'],
        'rush_att': ['rushing_car', 'rushing_att'],
        'rushing_attempts': ['rushing_car', 'rushing_att'],
        'receiving_yds': ['receiving_yds', 'receiving_yards'],
        'receiving_yards': ['receiving_yds', 'receiving_yards'],
        'receptions': ['receiving_rec', 'receiving_receptions'],
        'longest_reception': ['receiving_long', 'receiving_lng'],
        'tackles': ['defensive_tot', 'defensive_total', 'defensive_tackles'],
        'sacks': ['defensive_sacks', 'defensive_sack'],
        'field_goals_made': ['kicking_fg', 'kicking_fgm'],
        'extra_points_made': ['kicking_xp', 'kicking_xpm'],
    }
    if market_key in {'anytime_td', 'anytime_touchdown'}:
        rushing = first_existing_stat(stats, ['rushing_td', 'rushing_tds']) or 0
        receiving = first_existing_stat(stats, ['receiving_td', 'receiving_tds']) or 0
        returns = first_existing_stat(stats, ['kick_returns_td', 'punt_returns_td']) or 0
        return rushing + receiving + returns
    return first_existing_stat(stats, mapping.get(market_key, []))


def extract_player_and_market(pick):
    player = pick.get('player') or pick.get('player_name') or ''
    source_market = {
        'points_picks': 'Points',
        'rebounds_picks': 'Rebounds',
        'assists_picks': 'Assists',
        'threes_picks': 'Three Pointers Made',
        'steals_picks': 'Steals',
        'blocks_picks': 'Blocks',
        'combo_picks': pick.get('prop_type') or 'PRA',
    }.get(pick.get('_source_key'), '')
    market = (
        pick.get('market') or pick.get('prop_category')
        or pick.get('prop_type') or source_market
    )
    return str(player), str(market)


def collect_player_props(picks_data):
    if isinstance(picks_data.get('player_prop_picks'), list):
        return picks_data['player_prop_picks']
    combined = picks_data.get('picks', [])
    if isinstance(combined, list):
        props = [pick for pick in combined if canonical_pick_type(pick) == 'player_prop']
        if props:
            return props
    collected = []
    ignored = {'game_picks', 'nrfi_picks'}
    for key, value in picks_data.items():
        if key.endswith('_picks') and key not in ignored and isinstance(value, list):
            for pick in value:
                if isinstance(pick, dict):
                    copied = dict(pick)
                    copied['_source_key'] = key
                    collected.append(copied)
    return collected


def collect_game_picks(picks_data):
    if isinstance(picks_data.get('game_picks'), list):
        return picks_data['game_picks']
    combined = picks_data.get('picks', [])
    return [pick for pick in combined if canonical_pick_type(pick) in {'moneyline', 'spread', 'game_total'}] if isinstance(combined, list) else []


def grade_espn_sport_picks(sport, picks_data, player_stats, game_results, pick_date, graded_date):
    """Grade CFB/NFL/WNBA analyzer output and save record-only results."""
    summary = {}
    player_props = collect_player_props(picks_data)
    game_picks = collect_game_picks(picks_data)
    api_player_names = [record['name'] for record in player_stats.values()]

    for pick in player_props:
        player_name, market = extract_player_and_market(pick)
        matched_name, _ = fuzzy_match_player(player_name, api_player_names, threshold=0.82)
        record = player_stats.get(normalize_name(matched_name)) if matched_name else None
        try:
            line = float(pick.get('line') if pick.get('line') is not None else pick.get('prop_line'))
        except (TypeError, ValueError):
            line = None
        direction = str(pick.get('over_under') or pick.get('over_under_pick') or '').lower()
        if not direction:
            selection = str(pick.get('selection') or '').lower()
            direction = 'over' if ' over ' in f' {selection} ' else 'under' if ' under ' in f' {selection} ' else ''

        actual = prop_actual_value(sport, market, record['stats']) if record else None
        if record and actual is not None and line is not None and direction in {'over', 'under'}:
            result, _ = grade_result(actual, line, direction, record['did_play'])
        else:
            result = 'pending'

        category = f"Player {market or 'Prop'}"
        bucket = summary.setdefault(category, {'wins': 0, 'losses': 0, 'pushes': 0, 'pending': 0, 'profit': 0})
        counter_key = {'win': 'wins', 'loss': 'losses', 'push': 'pushes'}.get(result, 'pending')
        bucket[counter_key] += 1
        save_pick_result(
            pick_date, graded_date, sport, category, player_name,
            pick.get('game', ''), direction, line,
            pick.get('best_odds'), pick.get('best_book', ''), result, actual, 0,
        )

    for pick in game_picks:
        result, actual = grade_espn_game_pick(pick, game_results)
        pick_type = canonical_pick_type(pick)
        category_names = {'moneyline': 'Game ML', 'spread': 'Game Spread', 'game_total': 'Game OU'}
        category = category_names.get(pick_type, 'Game')
        bucket = summary.setdefault(category, {'wins': 0, 'losses': 0, 'pushes': 0, 'pending': 0, 'profit': 0})
        counter_key = {'win': 'wins', 'loss': 'losses', 'push': 'pushes'}.get(result, 'pending')
        bucket[counter_key] += 1
        line = pick.get('line') if pick.get('line') is not None else pick.get('fd_line')
        save_pick_result(
            pick_date, graded_date, sport, category,
            pick.get('team') or pick.get('selection') or pick.get('pick', ''),
            pick.get('game', ''), pick.get('over_under') or pick.get('over_under_pick', ''),
            line, pick.get('best_odds') or pick.get('fd_odds'), pick.get('best_book', ''),
            result, actual, 0,
        )

    print(f"   📊 {sport}: {len(player_props)} player props and {len(game_picks)} game picks processed")
    return summary

# ─────────────────────────────────────────────
# PARLAY GRADER
# ─────────────────────────────────────────────

def grade_parlay(parlay, pick_date, graded_date, sport):
    if not parlay or not parlay.get('legs'):
        return
    save_parlay_result(pick_date, graded_date, sport, parlay.get('legs', []), parlay.get('estimated_odds', 'N/A'), 'pending', 0)
    print(f"   📋 {sport} parlay saved as pending ({len(parlay.get('legs',[]))} legs)")

# ─────────────────────────────────────────────
# MAIN GRADER
# ─────────────────────────────────────────────

def run_grader():
    print(f"\n{'='*50}")
    print(f"📊 Grading yesterday's picks...")
    print(f"{'='*50}\n")

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    graded_date = datetime.now().strftime("%Y-%m-%d")
    init_db()

    mlb_picks = None
    nba_picks = None
    cfb_picks = None
    nfl_picks = None
    wnba_picks = None

    if os.path.exists(f"logs/{yesterday}_picks.json"):
        with open(f"logs/{yesterday}_picks.json", 'r') as f:
            mlb_picks = json.load(f)
        print(f"   📂 Loaded MLB picks for {yesterday}")
    else:
        print(f"   ⚠️ No MLB picks file for {yesterday}")

    if os.path.exists(f"logs/{yesterday}_nba_picks.json"):
        with open(f"logs/{yesterday}_nba_picks.json", 'r') as f:
            nba_picks = json.load(f)
        print(f"   📂 Loaded NBA picks for {yesterday}")
    else:
        print(f"   ⚠️ No NBA picks file for {yesterday}")

    for sport, filename in (
        ('CFB', f"logs/{yesterday}_cfb_picks.json"),
        ('NFL', f"logs/{yesterday}_nfl_picks.json"),
        ('WNBA', f"logs/{yesterday}_wnba_picks.json"),
    ):
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as file:
                    loaded = json.load(file)
                if sport == 'CFB':
                    cfb_picks = loaded
                elif sport == 'NFL':
                    nfl_picks = loaded
                else:
                    wnba_picks = loaded
                print(f"   📂 Loaded {sport} picks for {yesterday}")
            except (OSError, json.JSONDecodeError) as error:
                print(f"   ❌ Could not load {sport} picks: {error}")
        else:
            print(f"   ⚠️ No {sport} picks file for {yesterday}")

    if not any((mlb_picks, nba_picks, cfb_picks, nfl_picks, wnba_picks)):
        return None, get_cumulative_stats()

    mlb_player_stats, game_results = get_mlb_boxscores(yesterday) if mlb_picks else ({}, [])
    nba_player_stats = get_nba_boxscores(yesterday) if nba_picks else {}
    graded_summary = {}

    # MLB
    if mlb_picks and mlb_player_stats:
        if already_graded(yesterday, 'MLB'):
            print(f"   ⚠️ MLB picks for {yesterday} already graded — skipping")
            mlb_summary = get_daily_summary_from_db(yesterday)
            mlb_summary = {k.replace('MLB - ', ''): v for k, v in mlb_summary.items() if k.startswith('MLB')}
        else:
            print(f"\n⚾ Grading MLB picks...")
            mlb_summary = grade_mlb_picks(mlb_picks, mlb_player_stats, game_results, yesterday, graded_date)
            grade_parlay(mlb_picks.get('best_parlay'), yesterday, graded_date, 'MLB')
        graded_summary.update({f"MLB - {k}": v for k, v in mlb_summary.items()})

    # NRFI
    if mlb_picks:
        nrfi_picks_yesterday = mlb_picks.get('nrfi_picks', [])
        if nrfi_picks_yesterday:
            print(f"\n🎰 Grading NRFI picks...")
            nrfi_summary = grade_nrfi_picks(nrfi_picks_yesterday, yesterday, graded_date)
            graded_summary['MLB - NRFI'] = nrfi_summary
        else:
            print(f"   ℹ️ No NRFI picks found for {yesterday}")

    # NBA
    if nba_picks and nba_player_stats:
        if already_graded(yesterday, 'NBA'):
            print(f"   ⚠️ NBA picks for {yesterday} already graded — skipping")
            nba_summary = get_daily_summary_from_db(yesterday)
            nba_summary = {k.replace('NBA - ', ''): v for k, v in nba_summary.items() if k.startswith('NBA')}
        else:
            print(f"\n🏀 Grading NBA picks...")
            nba_summary = grade_nba_picks(nba_picks, nba_player_stats, yesterday, graded_date)
            grade_parlay(nba_picks.get('best_parlay'), yesterday, graded_date, 'NBA')
        graded_summary.update({f"NBA - {k}": v for k, v in nba_summary.items()})

    # CFB / NFL / WNBA
    for sport, sport_picks in (
        ('CFB', cfb_picks),
        ('NFL', nfl_picks),
        ('WNBA', wnba_picks),
    ):
        if not sport_picks:
            continue
        if already_graded(yesterday, sport):
            print(f"   ⚠️ {sport} picks for {yesterday} already graded — skipping")
            existing = get_daily_summary_from_db(yesterday)
            sport_summary = {
                key.replace(f'{sport} - ', ''): value
                for key, value in existing.items()
                if key.startswith(f'{sport} - ')
            }
        else:
            player_stats, sport_games = get_espn_results(sport, yesterday)
            if not sport_games:
                print(f"   ⏳ No completed {sport} games found; leaving picks ungraded")
                continue
            print(f"\n🏟️ Grading {sport} picks...")
            sport_summary = grade_espn_sport_picks(
                sport, sport_picks, player_stats, sport_games, yesterday, graded_date
            )
        graded_summary.update({f"{sport} - {key}": value for key, value in sport_summary.items()})

    cumulative = get_cumulative_stats()

    print(f"\n📊 RESULTS FOR {yesterday}")
    print(f"{'='*50}")
    for cat, stats in graded_summary.items():
        w = stats.get('wins', 0)
        l = stats.get('losses', 0)
        p = stats.get('pushes', 0)
        pend = stats.get('pending', 0)
        total = w + l + p
        rate = f"{w/total*100:.0f}%" if total > 0 else "—"
        print(f"  {cat:25} {w}W - {l}L - {p}P{f' ({pend} pending)' if pend else ''} | {rate}")

    print(f"\n📈 CUMULATIVE RECORD (All Time)")
    print(f"{'='*50}")
    for cat, stats in cumulative.items():
        if cat == 'OVERALL':
            continue
        print(f"  {cat:25} {stats['wins']}W - {stats['losses']}L - {stats['pushes']}P | {stats['win_rate']}%")
    if cumulative.get('OVERALL'):
        o = cumulative['OVERALL']
        print(f"\n  {'OVERALL':25} {o['wins']}W - {o['losses']}L - {o['pushes']}P | {o['win_rate']}%")

    return graded_summary, cumulative


def reset_grader_records():
    """Clear grading history only; preserve every non-grader database table."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pick_results")
    cursor.execute("DELETE FROM parlay_results")
    cursor.execute(
        "DELETE FROM sqlite_sequence WHERE name IN ('pick_results', 'parlay_results')"
    )
    conn.commit()
    conn.close()
    print("✅ Grader history reset")
    print("   Tracking will restart with the next saved picks.")
    print("   Games, pitchers, batters, and other data were preserved.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "--reset":
        reset_grader_records()
    else:
        run_grader()
