import sqlite3
import os

DB_PATH = "data/mlb_picks.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── GAMES ──────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scrape_date TEXT,
            game_date TEXT,
            game_time TEXT,
            home_team TEXT,
            away_team TEXT,
            ballpark TEXT,
            has_roof INTEGER DEFAULT 0,
            temp REAL,
            precip_pct REAL,
            wind_speed REAL,
            wind_dir TEXT,
            over_under REAL,
            home_ml TEXT,
            away_ml TEXT,
            home_spread TEXT,
            away_spread TEXT,
            home_spread_odds TEXT,
            away_spread_odds TEXT
        )
    ''')

    # ── STARTING PITCHERS ──────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pitchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            scrape_date TEXT,
            pitcher_name TEXT,
            team TEXT,
            handedness TEXT,
            is_home INTEGER,
            lineup_confirmed INTEGER DEFAULT 0,
            -- Season stats
            season_ip REAL,
            season_ipg REAL,
            season_whip REAL,
            season_hr INTEGER,
            season_hr9 REAL,
            season_barrel_pct REAL,
            season_hard_hit_pct REAL,
            season_fb_pct REAL,
            season_hr_fb_pct REAL,
            season_k9 REAL,
            season_k_pct REAL,
            -- vs LHB splits
            lhb_ip REAL,
            lhb_whip REAL,
            lhb_hr INTEGER,
            lhb_hr9 REAL,
            lhb_barrel_pct REAL,
            lhb_hard_hit_pct REAL,
            lhb_fb_pct REAL,
            lhb_hr_fb_pct REAL,
            -- vs RHB splits
            rhb_ip REAL,
            rhb_whip REAL,
            rhb_hr INTEGER,
            rhb_hr9 REAL,
            rhb_barrel_pct REAL,
            rhb_hard_hit_pct REAL,
            rhb_fb_pct REAL,
            rhb_hr_fb_pct REAL,
            -- FanDuel odds
            fd_k_line TEXT,
            fd_k_over TEXT,
            fd_k_under TEXT,
            FOREIGN KEY (game_id) REFERENCES games(id)
        )
    ''')

    # ── BATTERS ────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS batters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            scrape_date TEXT,
            batter_name TEXT,
            team TEXT,
            handedness TEXT,
            is_home INTEGER,
            lineup_confirmed INTEGER DEFAULT 0,
            batting_order INTEGER,
            opposing_pitcher_id INTEGER,
            split TEXT,
            -- Power/HR metrics
            hr_2025 INTEGER,
            hr_2026 INTEGER,
            hr_fb_pct REAL,
            barrel_pct REAL,
            hard_hit_pct REAL,
            fb_pct REAL,
            iso REAL,
            slg REAL,
            -- Contact/Hits metrics
            ba REAL,
            woba REAL,
            babip REAL,
            contact_pct REAL,
            -- Total Bases
            tb_per_game REAL,
            xba REAL,
            -- Exit Velocity
            l15_ev REAL,
            avg_ev REAL,
            max_ev REAL,
            -- Strikeout metrics
            k_pct REAL,
            swstr_pct REAL,
            chase_pct REAL,
            -- FanDuel odds
            fd_hr_odds TEXT,
            fd_hit_odds TEXT,
            fd_tb_line TEXT,
            fd_tb_over TEXT,
            fd_tb_under TEXT,
            fd_k_odds TEXT,
            FOREIGN KEY (game_id) REFERENCES games(id)
            FOREIGN KEY (opposing_pitcher_id) REFERENCES pitchers(id)
        )
    ''')

    # ── PARK FACTORS ───────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS park_factors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ballpark TEXT UNIQUE,
            hr_factor REAL,
            hits_factor REAL,
            runs_factor REAL,
            k_factor REAL,
            last_updated TEXT
        )
    ''')

    # ── DAILY PICKS ────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_date TEXT,
            pick_type TEXT,        -- 'single' or 'parlay'
            prop_category TEXT,    -- 'HR', 'Hit', 'TB', 'K', 'OU', 'ML', 'Spread'
            player_name TEXT,
            pitcher_name TEXT,
            team TEXT,
            game TEXT,
            game_time TEXT,
            ballpark TEXT,
            fd_odds TEXT,
            fd_line TEXT,
            over_under_pick TEXT,  -- 'over' or 'under' for props
            confidence_score REAL, -- 1-100
            confidence_tier TEXT,  -- 'Elite', 'High', 'Medium'
            key_factors TEXT,      -- JSON string of top reasons
            reasoning TEXT,
            result TEXT DEFAULT 'pending',
            actual_outcome TEXT,
            profit_loss REAL DEFAULT 0
        )
    ''')

    # ── PARLAYS ────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parlays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parlay_date TEXT,
            leg_count INTEGER,
            combined_odds TEXT,
            confidence_tier TEXT,
            result TEXT DEFAULT 'pending',
            profit_loss REAL DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parlay_legs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parlay_id INTEGER,
            pick_id INTEGER,
            leg_order INTEGER,
            FOREIGN KEY (parlay_id) REFERENCES parlays(id),
            FOREIGN KEY (pick_id) REFERENCES daily_picks(id)
        )
    ''')

    # ── PERFORMANCE TRACKING ───────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS model_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_date TEXT,
            prop_category TEXT,
            total_picks INTEGER,
            wins INTEGER,
            losses INTEGER,
            pushes INTEGER,
            win_rate REAL,
            roi REAL,
            avg_confidence REAL
        )
    ''')

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully")
    print("   Tables created: games, pitchers, batters, park_factors,")
    print("   daily_picks, parlays, parlay_legs, model_performance")

if __name__ == "__main__":
    # Clear and rebuild if exists
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("🗑️  Old database removed")
    init_db()