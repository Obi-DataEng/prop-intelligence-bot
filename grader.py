import requests
import json
import os
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from difflib import SequenceMatcher
import unicodedata

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
BASE_URL = "https://api.the-odds-api.com/v4"
MLB_STATS_URL = "https://statsapi.mlb.com/api/v1"
FLAT_BET = 5.00
DB_PATH = "data/mlb_picks.db"

# ─────────────────────────────────────────────
# NAME MATCHING
# ─────────────────────────────────────────────

def normalize_name(name):
    """Normalize player name for fuzzy matching"""
    if not name:
        return ""
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.lower().strip()
    for suffix in [' jr.', ' jr', ' sr.', ' sr', ' ii', ' iii', ' iv']:
        name = name.replace(suffix, '')
    return name.strip()

def fuzzy_match_player(pick_name, api_players, threshold=0.85):
    """Match pick player name to API player name"""
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
    """Calculate profit from American odds"""
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
    """
    Universal grading function for all props.
    Returns (result, profit_loss)
    """
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
        if actual > line:
            return 'win', calc_payout(odds, bet)
        else:
            return 'loss', -bet
    else:
        if actual < line:
            return 'win', calc_payout(odds, bet)
        else:
            return 'loss', -bet

# ─────────────────────────────────────────────
# MLB STATS API
# ─────────────────────────────────────────────

def get_mlb_boxscores(date_str):
    """Fetch all MLB box scores for a given date."""
    print(f"\n   🔍 Fetching MLB box scores for {date_str}...")
    try:
        schedule_url = f"{MLB_STATS_URL}/schedule"
        params = {
            "sportId": 1,
            "date": date_str,
            "hydrate": "boxscore"
        }
        r = requests.get(schedule_url, params=params, timeout=30)
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
                status = game.get('status', {}).get('abstractGameState', '')
                if status != 'Final':
                    continue

                game_pk = game.get('gamePk')
                home_team = game.get('teams', {}).get('home', {}).get('team', {}).get('name', '')
                away_team = game.get('teams', {}).get('away', {}).get('team', {}).get('name', '')
                home_score = game.get('teams', {}).get('home', {}).get('score', 0)
                away_score = game.get('teams', {}).get('away', {}).get('score', 0)

                game_results.append({
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_score': home_score,
                    'away_score': away_score,
                    'total': home_score + away_score
                })

                box_url = f"{MLB_STATS_URL}/game/{game_pk}/boxscore"
                box_r = requests.get(box_url, timeout=30)
                if box_r.status_code != 200:
                    continue

                box = box_r.json()

                for side in ['home', 'away']:
                    players = box.get('teams', {}).get(side, {}).get('players', {})
                    for pid, pdata in players.items():
                        name = pdata.get('person', {}).get('fullName', '')
                        stats = pdata.get('stats', {})
                        batting = stats.get('batting', {})
                        pitching = stats.get('pitching', {})

                        at_bats = batting.get('atBats', 0)
                        plate_appearances = batting.get('plateAppearances', 0)
                        innings_pitched = pitching.get('inningsPitched', '0')
                        did_play = plate_appearances > 0 or float(innings_pitched or 0) > 0

                        player_stats[name] = {
                            'did_play': did_play,
                            'hits': batting.get('hits', 0),
                            'home_runs': batting.get('homeRuns', 0),
                            'total_bases': batting.get('totalBases', 0),
                            'strikeouts_batter': batting.get('strikeOuts', 0),
                            'strikeouts_pitcher': pitching.get('strikeOuts', 0),
                            'at_bats': at_bats,
                            'plate_appearances': plate_appearances,
                            'innings_pitched': float(innings_pitched or 0)
                        }

        print(f"   ✅ {len(player_stats)} MLB players found across {len(game_results)} games")
        return player_stats, game_results

    except Exception as e:
        print(f"   ❌ MLB box score error: {e}")
        return {}, []

# ─────────────────────────────────────────────
# BALLDONTLIE NBA API
# ─────────────────────────────────────────────

def get_nba_boxscores(date_str):
    """Fetch all NBA box scores for a given date using NBA Stats API (no key needed)."""
    print(f"\n   🔍 Fetching NBA box scores for {date_str}...")
    try:
        # NBA Stats API — free, no key required
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://www.nba.com/',
            'Accept': 'application/json'
        }

        # Get scoreboard for the date
        scoreboard_url = "https://stats.nba.com/stats/scoreboardV2"
        params = {
            "GameDate": date_str,
            "LeagueID": "00",
            "DayOffset": "0"
        }
        r = requests.get(scoreboard_url, headers=headers, params=params, timeout=30)
        if r.status_code != 200:
            print(f"   ❌ NBA scoreboard error: {r.status_code}")
            return {}

        data = r.json()
        result_sets = {rs['name']: rs for rs in data.get('resultSets', [])}
        game_header = result_sets.get('GameHeader', {})
        headers_list = game_header.get('headers', [])
        rows = game_header.get('rowSet', [])

        game_ids = []
        game_id_idx = headers_list.index('GAME_ID') if 'GAME_ID' in headers_list else None
        status_idx = headers_list.index('GAME_STATUS_TEXT') if 'GAME_STATUS_TEXT' in headers_list else None

        for row in rows:
            if game_id_idx is not None:
                status = row[status_idx] if status_idx is not None else ''
                if 'Final' in str(status):
                    game_ids.append(row[game_id_idx])

        if not game_ids:
            print(f"   ⚠️ No final NBA games found for {date_str}")
            return {}

        player_stats = {}

        for game_id in game_ids:
            box_url = "https://stats.nba.com/stats/boxscoretraditionalv2"
            box_params = {
                "GameID": game_id,
                "StartPeriod": 0,
                "EndPeriod": 10,
                "StartRange": 0,
                "EndRange": 0,
                "RangeType": 0
            }
            box_r = requests.get(box_url, headers=headers, params=box_params, timeout=30)
            if box_r.status_code != 200:
                continue

            box_data = box_r.json()
            for rs in box_data.get('resultSets', []):
                if rs['name'] == 'PlayerStats':
                    h = rs['headers']
                    for row in rs['rowSet']:
                        rd = dict(zip(h, row))
                        name = rd.get('PLAYER_NAME', '')
                        min_str = rd.get('MIN', '0') or '0'
                        try:
                            if ':' in str(min_str):
                                mins = int(min_str.split(':')[0])
                            else:
                                mins = int(float(min_str))
                        except:
                            mins = 0

                        did_play = mins > 0
                        pts = rd.get('PTS', 0) or 0
                        reb = rd.get('REB', 0) or 0
                        ast = rd.get('AST', 0) or 0
                        fg3m = rd.get('FG3M', 0) or 0
                        stl = rd.get('STL', 0) or 0
                        blk = rd.get('BLK', 0) or 0

                        player_stats[name] = {
                            'did_play': did_play,
                            'pts': pts,
                            'reb': reb,
                            'ast': ast,
                            'fg3m': fg3m,
                            'stl': stl,
                            'blk': blk,
                            'pra': pts + reb + ast,
                            'pr': pts + reb,
                            'pa': pts + ast,
                            'min': mins
                        }

        print(f"   ✅ {len(player_stats)} NBA players found across {len(game_ids)} games")
        return player_stats

    except Exception as e:
        print(f"   ❌ NBA box score error: {e}")
        return {}

# ─────────────────────────────────────────────
# GAME PICK GRADING
# ─────────────────────────────────────────────

def grade_game_pick(pick, game_results):
    """Grade ML, Spread, O/U game picks from final scores"""
    game_str = pick.get('game', '')
    prop = pick.get('prop_category', '')
    pick_team = pick.get('pick', '')
    fd_line = pick.get('fd_line')
    ou_pick = pick.get('over_under_pick', '').lower()

    for game in game_results:
        home = game['home_team']
        away = game['away_team']

        if not (home in game_str or away in game_str or
                any(t in game_str for t in [home[:6], away[:6]])):
            continue

        home_score = game['home_score']
        away_score = game['away_score']
        total = game['total']

        if prop == 'ML':
            winner = home if home_score > away_score else away
            return ('win' if pick_team in winner else 'loss',
                    calc_payout(pick.get('fd_odds')) if pick_team in winner else -FLAT_BET)

        elif prop == 'OU':
            try:
                line = float(fd_line)
            except:
                return 'pending', 0
            if total == line:
                return 'push', 0
            if ou_pick == 'over':
                result = 'win' if total > line else 'loss'
            else:
                result = 'win' if total < line else 'loss'
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
    """Initialize database with correct schema"""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pick_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_date TEXT,
            graded_date TEXT,
            sport TEXT,
            category TEXT,
            player_name TEXT,
            game TEXT,
            over_under TEXT,
            line REAL,
            odds TEXT,
            best_book TEXT,
            result TEXT,
            actual_value REAL,
            bet_amount REAL,
            profit_loss REAL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parlay_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_date TEXT,
            graded_date TEXT,
            sport TEXT,
            legs TEXT,
            estimated_odds TEXT,
            result TEXT,
            bet_amount REAL,
            profit_loss REAL
        )
    ''')

    conn.commit()
    conn.close()

def already_graded(pick_date, sport):
    """Check if picks for this date/sport are already graded in the DB"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM pick_results
            WHERE pick_date = ? AND sport = ?
        ''', (pick_date, sport))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except:
        return False

def save_pick_result(pick_date, graded_date, sport, category, player_name,
                     game, over_under, line, odds, best_book,
                     result, actual_value, profit_loss):
    """Save a single graded pick to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO pick_results
        (pick_date, graded_date, sport, category, player_name, game,
         over_under, line, odds, best_book, result, actual_value,
         bet_amount, profit_loss)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (pick_date, graded_date, sport, category, player_name, game,
          over_under, line, odds, best_book, result, actual_value,
          FLAT_BET, profit_loss))
    conn.commit()
    conn.close()

def save_parlay_result(pick_date, graded_date, sport, legs,
                       estimated_odds, result, profit_loss):
    """Save parlay result to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO parlay_results
        (pick_date, graded_date, sport, legs, estimated_odds,
         result, bet_amount, profit_loss)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (pick_date, graded_date, sport, json.dumps(legs),
          estimated_odds, result, FLAT_BET, profit_loss))
    conn.commit()
    conn.close()

def get_cumulative_stats():
    """Get cumulative W-L-P and ROI per category across ALL dates"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    stats = {}

    try:
        # Per category stats — ALL time
        cursor.execute('''
            SELECT
                sport,
                category,
                COUNT(*) as total,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result = 'push' THEN 1 ELSE 0 END) as pushes,
                SUM(profit_loss) as total_profit,
                SUM(bet_amount) as total_wagered
            FROM pick_results
            WHERE result IN ('win', 'loss', 'push')
            GROUP BY sport, category
            ORDER BY sport, category
        ''')
        rows = cursor.fetchall()

        for row in rows:
            sport, cat, total, wins, losses, pushes, profit, wagered = row
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            roi = (profit / wagered * 100) if wagered and wagered > 0 else 0
            key = f"{sport} - {cat}"
            stats[key] = {
                'sport': sport,
                'category': cat,
                'wins': wins or 0,
                'losses': losses or 0,
                'pushes': pushes or 0,
                'win_rate': round(win_rate, 1),
                'total_profit': round(profit or 0, 2),
                'roi': round(roi, 1)
            }

        # Parlay stats — ALL time
        cursor.execute('''
            SELECT
                sport,
                COUNT(*) as total,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(profit_loss) as total_profit,
                SUM(bet_amount) as total_wagered
            FROM parlay_results
            WHERE result IN ('win', 'loss')
            GROUP BY sport
        ''')
        parlay_rows = cursor.fetchall()

        for row in parlay_rows:
            sport, total, wins, losses, profit, wagered = row
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            roi = (profit / wagered * 100) if wagered and wagered > 0 else 0
            key = f"{sport} - Parlay"
            stats[key] = {
                'sport': sport,
                'category': 'Parlay',
                'wins': wins or 0,
                'losses': losses or 0,
                'pushes': 0,
                'win_rate': round(win_rate, 1),
                'total_profit': round(profit or 0, 2),
                'roi': round(roi, 1)
            }

        # Overall — ALL time
        cursor.execute('''
            SELECT
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END),
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END),
                SUM(CASE WHEN result = 'push' THEN 1 ELSE 0 END),
                SUM(profit_loss),
                SUM(bet_amount)
            FROM (
                SELECT result, profit_loss, bet_amount FROM pick_results
                WHERE result IN ('win', 'loss', 'push')
                UNION ALL
                SELECT result, profit_loss, bet_amount FROM parlay_results
                WHERE result IN ('win', 'loss')
            )
        ''')
        row = cursor.fetchone()
        if row:
            wins, losses, pushes, profit, wagered = row
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            roi = (profit / wagered * 100) if wagered and wagered > 0 else 0
            stats['OVERALL'] = {
                'wins': wins or 0,
                'losses': losses or 0,
                'pushes': pushes or 0,
                'win_rate': round(win_rate, 1),
                'total_profit': round(profit or 0, 2),
                'roi': round(roi, 1)
            }

    except Exception as e:
        print(f"   ❌ Stats error: {e}")
        import traceback
        traceback.print_exc()

    conn.close()
    return stats

def get_daily_summary_from_db(pick_date):
    """Pull today's graded results from DB for the email summary"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    summary = {}

    try:
        cursor.execute('''
            SELECT
                sport,
                category,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result = 'push' THEN 1 ELSE 0 END) as pushes,
                SUM(CASE WHEN result = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(profit_loss) as profit
            FROM pick_results
            WHERE pick_date = ?
            GROUP BY sport, category
        ''', (pick_date,))
        rows = cursor.fetchall()

        for row in rows:
            sport, cat, wins, losses, pushes, pending, profit = row
            key = f"{sport} - {cat}"
            summary[key] = {
                'wins': wins or 0,
                'losses': losses or 0,
                'pushes': pushes or 0,
                'pending': pending or 0,
                'profit': round(profit or 0, 2)
            }

    except Exception as e:
        print(f"   ❌ Daily summary error: {e}")

    conn.close()
    return summary

# ─────────────────────────────────────────────
# MLB GRADER
# ─────────────────────────────────────────────

def grade_mlb_picks(picks_data, player_stats, game_results, pick_date, graded_date):
    """Grade all MLB picks and save to DB"""
    summary = {}
    api_players = list(player_stats.keys())

    mlb_categories = {
        'hr_picks':           ('HR', 'home_runs', None),
        'hits_picks':         ('Hits', 'hits', 'over_under_pick'),
        'total_bases_picks':  ('TB', 'total_bases', 'over_under_pick'),
        'strikeout_picks':    ('K', None, 'over_under_pick'),
    }

    for key, (cat, stat_field, ou_field) in mlb_categories.items():
        picks = picks_data.get(key, [])
        wins = losses = pushes = pending = 0
        profit = 0

        for pick in picks:
            player_name = pick.get('player_name', '')
            pick_type = pick.get('pick_type', 'batter')
            line = pick.get('fd_line')
            ou = pick.get(ou_field, 'over') if ou_field else 'over'
            odds = pick.get('fd_odds') or pick.get('czs_odds') or pick.get('mgm_odds')

            if cat == 'HR':
                ou = 'over'
                line = 0.5

            if cat == 'K':
                stat_field = 'strikeouts_pitcher' if 'pitcher' in str(pick_type).lower() \
                             else 'strikeouts_batter'

            matched_name, score = fuzzy_match_player(player_name, api_players)

            if not matched_name:
                result, pl = 'pending', 0
                actual_value = None
                pending += 1
            else:
                pstats = player_stats[matched_name]
                did_play = pstats['did_play']
                actual_value = pstats.get(stat_field, 0)

                try:
                    result, pl = grade_result(actual_value, line, ou, did_play, odds)
                except Exception as e:
                    result, pl = 'pending', 0
                    actual_value = None

                if result == 'win': wins += 1
                elif result == 'loss': losses += 1
                elif result == 'push': pushes += 1
                else: pending += 1

                profit += pl

            save_pick_result(
                pick_date, graded_date, 'MLB', cat,
                player_name, pick.get('game', ''),
                ou, line, odds, pick.get('best_book', ''),
                result, actual_value, pl
            )

        summary[cat] = {
            'wins': wins, 'losses': losses,
            'pushes': pushes, 'pending': pending,
            'profit': round(profit, 2)
        }

    # Game picks
    game_picks = picks_data.get('game_picks', [])
    ml_wins = ml_losses = ml_pushes = 0
    spread_wins = spread_losses = spread_pushes = 0
    ou_wins = ou_losses = ou_pushes = 0
    ml_profit = spread_profit = ou_profit = 0

    for pick in game_picks:
        prop = pick.get('prop_category', 'ML')
        result, pl = grade_game_pick(pick, game_results)

        save_pick_result(
            pick_date, graded_date, 'MLB', f"Game {prop}",
            pick.get('pick', ''), pick.get('game', ''),
            pick.get('over_under_pick', ''),
            pick.get('fd_line'), pick.get('fd_odds'),
            pick.get('best_book', ''), result, None, pl
        )

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

    summary['Game ML'] = {'wins': ml_wins, 'losses': ml_losses,
                           'pushes': ml_pushes, 'pending': 0,
                           'profit': round(ml_profit, 2)}
    summary['Game Spread'] = {'wins': spread_wins, 'losses': spread_losses,
                               'pushes': spread_pushes, 'pending': 0,
                               'profit': round(spread_profit, 2)}
    summary['Game OU'] = {'wins': ou_wins, 'losses': ou_losses,
                           'pushes': ou_pushes, 'pending': 0,
                           'profit': round(ou_profit, 2)}

    return summary

# ─────────────────────────────────────────────
# NBA GRADER
# ─────────────────────────────────────────────

def grade_nba_picks(nba_picks_data, nba_player_stats, pick_date, graded_date):
    """Grade all NBA picks and save to DB"""
    summary = {}
    api_players = list(nba_player_stats.keys())

    nba_categories = {
        'points_picks':   ('Points', 'pts'),
        'rebounds_picks': ('Rebounds', 'reb'),
        'assists_picks':  ('Assists', 'ast'),
        'threes_picks':   ('Threes', 'fg3m'),
    }

    for key, (cat, stat_field) in nba_categories.items():
        picks = nba_picks_data.get(key, [])
        wins = losses = pushes = pending = 0
        profit = 0

        for pick in picks:
            player_name = pick.get('player_name', '')
            line = pick.get('prop_line')
            ou = pick.get('over_under', 'OVER')
            odds = pick.get('best_odds')

            matched_name, score = fuzzy_match_player(player_name, api_players)

            if not matched_name:
                result, pl = 'pending', 0
                actual_value = None
                pending += 1
            else:
                pstats = nba_player_stats[matched_name]
                did_play = pstats['did_play']
                actual_value = pstats.get(stat_field, 0)
                result, pl = grade_result(actual_value, line, ou, did_play, odds)

                if result == 'win': wins += 1
                elif result == 'loss': losses += 1
                elif result == 'push': pushes += 1
                else: pending += 1
                profit += pl

            save_pick_result(
                pick_date, graded_date, 'NBA', cat,
                player_name, pick.get('team', '') + ' vs ' + pick.get('opponent', ''),
                ou, line, odds, pick.get('best_book', ''),
                result, actual_value, pl
            )

        summary[cat] = {
            'wins': wins, 'losses': losses,
            'pushes': pushes, 'pending': pending,
            'profit': round(profit, 2)
        }

    # Combo picks
    combo_picks = nba_picks_data.get('combo_picks', [])
    wins = losses = pushes = pending = 0
    profit = 0

    combo_stat_map = {
        'PRA': 'pra', 'PR': 'pr', 'PA': 'pa',
        'pts': 'pts', 'reb': 'reb', 'ast': 'ast'
    }

    for pick in combo_picks:
        player_name = pick.get('player_name', '')
        line = pick.get('prop_line')
        ou = pick.get('over_under', 'OVER')
        odds = pick.get('best_odds')
        prop_type = pick.get('prop_type', 'PRA').upper()
        stat_field = combo_stat_map.get(prop_type, 'pra')

        matched_name, score = fuzzy_match_player(player_name, api_players)

        if not matched_name:
            result, pl = 'pending', 0
            actual_value = None
            pending += 1
        else:
            pstats = nba_player_stats[matched_name]
            did_play = pstats['did_play']
            actual_value = pstats.get(stat_field, 0)
            result, pl = grade_result(actual_value, line, ou, did_play, odds)

            if result == 'win': wins += 1
            elif result == 'loss': losses += 1
            elif result == 'push': pushes += 1
            else: pending += 1
            profit += pl

        save_pick_result(
            pick_date, graded_date, 'NBA', 'Combo',
            player_name, pick.get('team', '') + ' vs ' + pick.get('opponent', ''),
            ou, line, odds, pick.get('best_book', ''),
            result, actual_value, pl
        )

    summary['Combo'] = {
        'wins': wins, 'losses': losses,
        'pushes': pushes, 'pending': pending,
        'profit': round(profit, 2)
    }

    # NBA Game picks — pending until scores added
    game_picks = nba_picks_data.get('game_picks', [])
    wins = losses = pushes = pending = 0

    for pick in game_picks:
        pick_team = pick.get('pick', '')
        line = pick.get('line')
        odds = line
        game = pick.get('game', '')

        result, pl = 'pending', 0
        pending += 1

        save_pick_result(
            pick_date, graded_date, 'NBA', 'Game',
            pick_team, game, 'over', None, odds,
            pick.get('best_book', ''), result, None, pl
        )

    summary['Game'] = {
        'wins': wins, 'losses': losses,
        'pushes': pushes, 'pending': pending,
        'profit': 0
    }

    return summary

# ─────────────────────────────────────────────
# PARLAY GRADER
# ─────────────────────────────────────────────

def grade_parlay(parlay, pick_date, graded_date, sport):
    """Save parlay as pending for manual grading"""
    if not parlay or not parlay.get('legs'):
        return

    legs = parlay.get('legs', [])
    estimated_odds = parlay.get('estimated_odds', 'N/A')

    save_parlay_result(
        pick_date, graded_date, sport,
        legs, estimated_odds, 'pending', 0
    )
    print(f"   📋 {sport} parlay saved as pending ({len(legs)} legs)")

# ─────────────────────────────────────────────
# MAIN GRADER
# ─────────────────────────────────────────────

def run_grader():
    """Main grader — grades yesterday's picks, returns daily + cumulative stats"""
    print(f"\n{'='*50}")
    print(f"📊 Grading yesterday's picks...")
    print(f"{'='*50}\n")

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    graded_date = datetime.now().strftime("%Y-%m-%d")

    init_db()

    mlb_file = f"logs/{yesterday}_picks.json"
    nba_file = f"logs/{yesterday}_nba_picks.json"

    mlb_picks = None
    nba_picks = None

    if os.path.exists(mlb_file):
        with open(mlb_file, 'r') as f:
            mlb_picks = json.load(f)
        print(f"   📂 Loaded MLB picks for {yesterday}")
    else:
        print(f"   ⚠️ No MLB picks file for {yesterday}")

    if os.path.exists(nba_file):
        with open(nba_file, 'r') as f:
            nba_picks = json.load(f)
        print(f"   📂 Loaded NBA picks for {yesterday}")
    else:
        print(f"   ⚠️ No NBA picks file for {yesterday}")

    if not mlb_picks and not nba_picks:
        cumulative = get_cumulative_stats()
        return None, cumulative

    # Fetch box scores
    mlb_player_stats, game_results = get_mlb_boxscores(yesterday) if mlb_picks else ({}, [])
    nba_player_stats = get_nba_boxscores(yesterday) if nba_picks else {}

    graded_summary = {}

    # Grade MLB — skip if already graded
    if mlb_picks and mlb_player_stats:
        if already_graded(yesterday, 'MLB'):
            print(f"   ⚠️ MLB picks for {yesterday} already graded — skipping duplicates")
            mlb_summary = get_daily_summary_from_db(yesterday)
            mlb_summary = {k.replace('MLB - ', ''): v
                           for k, v in mlb_summary.items() if k.startswith('MLB')}
        else:
            print(f"\n⚾ Grading MLB picks...")
            mlb_summary = grade_mlb_picks(
                mlb_picks, mlb_player_stats,
                game_results, yesterday, graded_date
            )
            grade_parlay(mlb_picks.get('best_parlay'), yesterday, graded_date, 'MLB')

        graded_summary.update({f"MLB - {k}": v for k, v in mlb_summary.items()})

    # Grade NBA — skip if already graded
    if nba_picks and nba_player_stats:
        if already_graded(yesterday, 'NBA'):
            print(f"   ⚠️ NBA picks for {yesterday} already graded — skipping duplicates")
            nba_summary = get_daily_summary_from_db(yesterday)
            nba_summary = {k.replace('NBA - ', ''): v
                           for k, v in nba_summary.items() if k.startswith('NBA')}
        else:
            print(f"\n🏀 Grading NBA picks...")
            nba_summary = grade_nba_picks(
                nba_picks, nba_player_stats,
                yesterday, graded_date
            )
            grade_parlay(nba_picks.get('best_parlay'), yesterday, graded_date, 'NBA')

        graded_summary.update({f"NBA - {k}": v for k, v in nba_summary.items()})

    # Get cumulative stats across ALL dates
    cumulative = get_cumulative_stats()

    # Print daily summary
    print(f"\n📊 RESULTS FOR {yesterday}")
    print(f"{'='*50}")
    for cat, stats in graded_summary.items():
        w = stats['wins']
        l = stats['losses']
        p = stats['pushes']
        pend = stats.get('pending', 0)
        total = w + l + p
        rate = f"{w/total*100:.0f}%" if total > 0 else "—"
        print(f"  {cat:25} {w}W - {l}L - {p}P"
              f"{f' ({pend} pending)' if pend else ''}"
              f" | {rate} | ${stats['profit']:+.2f}")

    # Print cumulative
    print(f"\n📈 CUMULATIVE RECORD (All Time)")
    print(f"{'='*50}")
    for cat, stats in cumulative.items():
        if cat == 'OVERALL':
            continue
        w = stats['wins']
        l = stats['losses']
        p = stats['pushes']
        profit = stats['total_profit']
        roi = stats['roi']
        print(f"  {cat:25} {w}W - {l}L - {p}P"
              f" | {stats['win_rate']}% | ${profit:+.2f} | ROI: {roi:+.1f}%")

    if cumulative.get('OVERALL'):
        o = cumulative['OVERALL']
        print(f"\n  {'OVERALL':25} {o['wins']}W - {o['losses']}L - {o['pushes']}P"
              f" | {o['win_rate']}% | ${o['total_profit']:+.2f}"
              f" | ROI: {o['roi']:+.1f}%")

    return graded_summary, cumulative


if __name__ == "__main__":
    run_grader()