import requests
import json
import os
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
BASE_URL = "https://api.the-odds-api.com/v4"
FLAT_BET = 5.00
DB_PATH = "data/mlb_picks.db"

def get_mlb_scores(date_str):
    """Fetch completed MLB game scores from Odds API"""
    url = f"{BASE_URL}/sports/baseball_mlb/scores"
    params = {
        "apiKey": API_KEY,
        "daysFrom": 1,
    }
    response = requests.get(url, params=params)
    print(f"   📊 Requests remaining: {response.headers.get('x-requests-remaining')}")

    if response.status_code != 200:
        print(f"   ❌ Scores error: {response.status_code}")
        return []

    games = response.json()
    completed = [g for g in games if g.get('completed')]
    print(f"   ✅ Found {len(completed)} completed games")
    return completed

def calc_payout(odds, bet=FLAT_BET):
    """Calculate profit from American odds"""
    if odds is None:
        return 0
    odds = int(str(odds).replace('+', ''))
    if odds > 0:
        return round(bet * odds / 100, 2)
    else:
        return round(bet * 100 / abs(odds), 2)

def grade_game_pick(pick, scores):
    """Grade ML, spread, and O/U game picks"""
    game_str = pick.get('game', '')
    prop = pick.get('prop_category', '')
    pick_team = pick.get('pick', '')
    fd_line = pick.get('fd_line')

    for game in scores:
        home = game.get('home_team', '')
        away = game.get('away_team', '')

        # Match game
        if not (home in game_str or away in game_str):
            continue

        scores_data = game.get('scores')
        if not scores_data or len(scores_data) < 2:
            return 'pending'

        home_score = next((s['score'] for s in scores_data if s['name'] == home), None)
        away_score = next((s['score'] for s in scores_data if s['name'] == away), None)

        if home_score is None or away_score is None:
            return 'pending'

        home_score = int(home_score)
        away_score = int(away_score)
        total = home_score + away_score

        if prop == 'ML':
            winner = home if home_score > away_score else away
            return 'win' if pick_team in winner else 'loss'

        elif prop == 'OU':
            ou_pick = pick.get('over_under_pick', '').lower()
            line = float(fd_line) if fd_line else 0
            if total == line:
                return 'push'
            if ou_pick == 'over':
                return 'win' if total > line else 'loss'
            else:
                return 'win' if total < line else 'loss'

        elif prop == 'Spread':
            line = float(fd_line) if fd_line else 0
            if pick_team in home:
                margin = home_score - away_score
            else:
                margin = away_score - home_score
            if margin + line == 0:
                return 'push'
            return 'win' if margin + line > 0 else 'loss'

    return 'pending'

def grade_player_prop(pick, scores):
    """
    Player props (HR, Hits, TB, K) can't be auto-graded from scores API.
    We mark them pending and use a simplified hit rate assumption.
    In future, integrate with MLB Stats API for box scores.
    """
    return 'pending'

def load_yesterdays_picks():
    """Load picks from yesterday's JSON file"""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    filepath = f"logs/{yesterday}_picks.json"

    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f), yesterday
    else:
        print(f"   ⚠️ No picks file for {yesterday}")
        return None, yesterday

def save_results_to_db(results, date_str):
    """Save graded results to SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create results table if not exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pick_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_date TEXT,
            graded_date TEXT,
            prop_category TEXT,
            player_name TEXT,
            game TEXT,
            pick_type TEXT,
            fd_odds TEXT,
            fd_line TEXT,
            over_under_pick TEXT,
            result TEXT,
            bet_amount REAL,
            profit_loss REAL,
            best_book TEXT
        )
    ''')

    # Create cumulative stats table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cumulative_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stat_date TEXT,
            prop_category TEXT,
            total_picks INTEGER,
            wins INTEGER,
            losses INTEGER,
            pushes INTEGER,
            pending INTEGER,
            win_rate REAL,
            total_wagered REAL,
            total_profit REAL,
            roi REAL
        )
    ''')

    for r in results:
        cursor.execute('''
            INSERT INTO pick_results
            (pick_date, graded_date, prop_category, player_name, game,
             pick_type, fd_odds, fd_line, over_under_pick, result,
             bet_amount, profit_loss, best_book)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            r['pick_date'], date_str,
            r.get('prop_category'), r.get('player_name'),
            r.get('game'), r.get('pick_type'),
            r.get('fd_odds'), r.get('fd_line'),
            r.get('over_under_pick'), r.get('result'),
            r.get('bet_amount', FLAT_BET), r.get('profit_loss', 0),
            r.get('best_book')
        ))

    conn.commit()
    conn.close()
    print(f"   ✅ {len(results)} results saved to database")

def get_cumulative_stats():
    """Pull cumulative stats from database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT
                prop_category,
                COUNT(*) as total,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result = 'push' THEN 1 ELSE 0 END) as pushes,
                SUM(CASE WHEN result = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(profit_loss) as total_profit,
                SUM(bet_amount) as total_wagered
            FROM pick_results
            WHERE result != 'pending'
            GROUP BY prop_category
        ''')
        rows = cursor.fetchall()

        stats = {}
        for row in rows:
            cat, total, wins, losses, pushes, pending, profit, wagered = row
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            roi = (profit / wagered * 100) if wagered > 0 else 0
            stats[cat] = {
                'total': total,
                'wins': wins,
                'losses': losses,
                'pushes': pushes,
                'win_rate': round(win_rate, 1),
                'total_profit': round(profit, 2),
                'roi': round(roi, 1)
            }

        # Overall stats
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result = 'push' THEN 1 ELSE 0 END) as pushes,
                SUM(profit_loss) as total_profit,
                SUM(bet_amount) as total_wagered
            FROM pick_results
            WHERE result != 'pending'
        ''')
        row = cursor.fetchone()
        if row:
            total, wins, losses, pushes, profit, wagered = row
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            roi = (profit / wagered * 100) if wagered > 0 else 0
            stats['OVERALL'] = {
                'total': total,
                'wins': wins,
                'losses': losses,
                'pushes': pushes,
                'win_rate': round(win_rate, 1),
                'total_profit': round(profit, 2),
                'roi': round(roi, 1)
            }

    except Exception as e:
        print(f"   ⚠️ Stats error: {e}")
        stats = {}

    conn.close()
    return stats

def run_grader():
    """Main grader function"""
    print(f"\n{'='*50}")
    print(f"📊 Grading yesterday's picks...")
    print(f"{'='*50}\n")

    # Load yesterday's picks
    picks_data, yesterday = load_yesterdays_picks()
    if not picks_data:
        return None, None

    # Get scores
    print(f"🔍 Fetching completed scores...")
    scores = get_mlb_scores(yesterday)

    # Grade all picks
    all_picks = []
    categories = {
        'hr_picks': 'HR',
        'hits_picks': 'Hit',
        'total_bases_picks': 'TB',
        'strikeout_picks': 'K',
        'game_picks': 'Game'
    }

    graded_summary = {}

    for key, category in categories.items():
        picks = picks_data.get(key, [])
        wins = losses = pushes = pending = 0
        profit = 0

        for pick in picks:
            # Grade game picks automatically, player props as pending
            if category == 'Game':
                result = grade_game_pick(pick, scores)
            else:
                result = grade_player_prop(pick, scores)

            # Calculate P&L
            if result == 'win':
                pl = calc_payout(pick.get('fd_odds'))
                wins += 1
            elif result == 'loss':
                pl = -FLAT_BET
                losses += 1
            elif result == 'push':
                pl = 0
                pushes += 1
            else:
                pl = 0
                pending += 1

            profit += pl

            all_picks.append({
                'pick_date': yesterday,
                'prop_category': category,
                'player_name': pick.get('player_name') or pick.get('pick'),
                'game': pick.get('game'),
                'pick_type': pick.get('pick_type', 'single'),
                'fd_odds': pick.get('fd_odds'),
                'fd_line': pick.get('fd_line'),
                'over_under_pick': pick.get('over_under_pick'),
                'result': result,
                'bet_amount': FLAT_BET,
                'profit_loss': pl,
                'best_book': pick.get('best_book')
            })

        graded_summary[category] = {
            'wins': wins,
            'losses': losses,
            'pushes': pushes,
            'pending': pending,
            'profit': round(profit, 2)
        }

    # Save to DB
    save_results_to_db(all_picks, datetime.now().strftime("%Y-%m-%d"))

    # Get cumulative stats
    cumulative = get_cumulative_stats()

    print(f"\n📊 YESTERDAY'S RESULTS ({yesterday})")
    print(f"{'='*40}")
    for cat, stats in graded_summary.items():
        w, l, p, pend = stats['wins'], stats['losses'], stats['pushes'], stats['pending']
        total = w + l + p
        rate = f"{w/total*100:.0f}%" if total > 0 else "N/A"
        print(f"  {cat}: {w}W-{l}L-{p}P ({pend} pending) | {rate} | ${stats['profit']:+.2f}")

    if cumulative.get('OVERALL'):
        o = cumulative['OVERALL']
        print(f"\n📈 CUMULATIVE RECORD")
        print(f"{'='*40}")
        print(f"  Overall: {o['wins']}W-{o['losses']}L-{o['pushes']}P ({o['win_rate']}%)")
        print(f"  Total P&L: ${o['total_profit']:+.2f}")
        print(f"  ROI: {o['roi']:+.1f}%")

    return graded_summary, cumulative

if __name__ == "__main__":
    run_grader()