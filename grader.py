import requests
import json
import os
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from difflib import SequenceMatcher
import unicodedata

load_dotenv()

MLB_STATS_URL = "https://statsapi.mlb.com/api/v1"
FLAT_BET = 5.00
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
# PAYOUT CALCULATION
# ─────────────────────────────────────────────

def calc_payout(odds, bet=FLAT_BET):
    if not odds:
        return 0
    try:
        odds = int(str(odds).replace('+', ''))
        if odds > 0:
            return round(bet * odds / 100, 2)
        else:
            return round(bet * 100 / abs(odds), 2)
    except:
        return 0

# ─────────────────────────────────────────────
# GRADING CORE
# ─────────────────────────────────────────────

def grade_result(actual, line, over_under, did_play, odds, bet=FLAT_BET):
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
        return ('win', calc_payout(odds, bet)) if actual > line else ('loss', -bet)
    else:
        return ('win', calc_payout(odds, bet)) if actual < line else ('loss', -bet)

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
            return ('win' if pick_team in winner else 'loss', calc_payout(pick.get('fd_odds')) if pick_team in winner else -FLAT_BET)
        elif prop == 'OU':
            try:
                line = float(fd_line)
            except:
                return 'pending', 0
            if total == line:
                return 'push', 0
            result = 'win' if (ou_pick == 'over' and total > line) or (ou_pick != 'over' and total < line) else 'loss'
            return (result, calc_payout(pick.get('fd_odds')) if result == 'win' else -FLAT_BET)
        elif prop == 'Spread':
            try:
                line = float(fd_line)
            except:
                return 'pending', 0
            margin = (home_score - away_score) if pick_team in home else (away_score - home_score)
            if margin + line == 0:
                return 'push', 0
            result = 'win' if margin + line > 0 else 'loss'
            return (result, calc_payout(pick.get('fd_odds')) if result == 'win' else -FLAT_BET)
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
        odds TEXT, best_book TEXT, result TEXT, actual_value REAL,
        bet_amount REAL, profit_loss REAL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS parlay_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pick_date TEXT, graded_date TEXT, sport TEXT, legs TEXT,
        estimated_odds TEXT, result TEXT, bet_amount REAL, profit_loss REAL)''')
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
        (pick_date, graded_date, sport, category, player_name, game, over_under, line, odds, best_book, result, actual_value, bet_amount, profit_loss)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (pick_date, graded_date, sport, category, player_name, game, over_under, line, odds, best_book, result, actual_value, FLAT_BET, profit_loss))
    conn.commit()
    conn.close()

def save_parlay_result(pick_date, graded_date, sport, legs, estimated_odds, result, profit_loss):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO parlay_results (pick_date, graded_date, sport, legs, estimated_odds, result, bet_amount, profit_loss)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (pick_date, graded_date, sport, json.dumps(legs), estimated_odds, result, FLAT_BET, profit_loss))
    conn.commit()
    conn.close()

def get_cumulative_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    stats = {}
    try:
        cursor.execute('''SELECT sport, category,
            COUNT(*),
            SUM(CASE WHEN result='win' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='push' THEN 1 ELSE 0 END),
            SUM(profit_loss), SUM(bet_amount)
            FROM pick_results WHERE result IN ('win','loss','push')
            GROUP BY sport, category ORDER BY sport, category''')
        for row in cursor.fetchall():
            sport, cat, total, wins, losses, pushes, profit, wagered = row
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            roi = (profit / wagered * 100) if wagered and wagered > 0 else 0
            stats[f"{sport} - {cat}"] = {
                'sport': sport, 'category': cat,
                'wins': wins or 0, 'losses': losses or 0, 'pushes': pushes or 0,
                'win_rate': round(win_rate, 1), 'total_profit': round(profit or 0, 2), 'roi': round(roi, 1)
            }
        cursor.execute('''SELECT sport,
            COUNT(*),
            SUM(CASE WHEN result='win' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END),
            SUM(profit_loss), SUM(bet_amount)
            FROM parlay_results WHERE result IN ('win','loss') GROUP BY sport''')
        for row in cursor.fetchall():
            sport, total, wins, losses, profit, wagered = row
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            roi = (profit / wagered * 100) if wagered and wagered > 0 else 0
            stats[f"{sport} - Parlay"] = {
                'sport': sport, 'category': 'Parlay',
                'wins': wins or 0, 'losses': losses or 0, 'pushes': 0,
                'win_rate': round(win_rate, 1), 'total_profit': round(profit or 0, 2), 'roi': round(roi, 1)
            }
        cursor.execute('''SELECT
            SUM(CASE WHEN result='win' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END),
            SUM(CASE WHEN result='push' THEN 1 ELSE 0 END),
            SUM(profit_loss), SUM(bet_amount)
            FROM (
                SELECT result, profit_loss, bet_amount FROM pick_results WHERE result IN ('win','loss','push')
                UNION ALL
                SELECT result, profit_loss, bet_amount FROM parlay_results WHERE result IN ('win','loss')
            )''')
        row = cursor.fetchone()
        if row:
            wins, losses, pushes, profit, wagered = row
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            roi = (profit / wagered * 100) if wagered and wagered > 0 else 0
            stats['OVERALL'] = {
                'wins': wins or 0, 'losses': losses or 0, 'pushes': pushes or 0,
                'win_rate': round(win_rate, 1), 'total_profit': round(profit or 0, 2), 'roi': round(roi, 1)
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
            SUM(CASE WHEN result='pending' THEN 1 ELSE 0 END),
            SUM(profit_loss)
            FROM pick_results WHERE pick_date = ? GROUP BY sport, category''', (pick_date,))
        for row in cursor.fetchall():
            sport, cat, wins, losses, pushes, pending, profit = row
            summary[f"{sport} - {cat}"] = {
                'wins': wins or 0, 'losses': losses or 0, 'pushes': pushes or 0,
                'pending': pending or 0, 'profit': round(profit or 0, 2)
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
            (pick_date, graded_date, sport, category, player_name, game, over_under, line, odds, best_book, result, actual_value, bet_amount, profit_loss)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (pick_date, graded_date, 'MLB', 'NRFI', pitchers, game, bet, None, None, 'N/A', result, None, 0, 0))
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

    if not mlb_picks and not nba_picks:
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
        profit_str = f" | ${stats['profit']:+.2f}" if stats.get('profit') != 0 else " | W/L only"
        print(f"  {cat:25} {w}W - {l}L - {p}P{f' ({pend} pending)' if pend else ''} | {rate}{profit_str}")

    print(f"\n📈 CUMULATIVE RECORD (All Time)")
    print(f"{'='*50}")
    for cat, stats in cumulative.items():
        if cat == 'OVERALL':
            continue
        print(f"  {cat:25} {stats['wins']}W - {stats['losses']}L - {stats['pushes']}P | {stats['win_rate']}% | ${stats['total_profit']:+.2f} | ROI: {stats['roi']:+.1f}%")
    if cumulative.get('OVERALL'):
        o = cumulative['OVERALL']
        print(f"\n  {'OVERALL':25} {o['wins']}W - {o['losses']}L - {o['pushes']}P | {o['win_rate']}% | ${o['total_profit']:+.2f} | ROI: {o['roi']:+.1f}%")

    return graded_summary, cumulative


if __name__ == "__main__":
    run_grader()