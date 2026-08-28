import sqlite3

conn = sqlite3.connect('data/mlb_picks.db')
cursor = conn.cursor()

tables = ['games', 'daily_picks', 'parlays', 'parlay_legs', 'model_performance']

for table in tables:
    print(f'\n--- {table.upper()} ---')
    cursor.execute(f'SELECT * FROM {table} LIMIT 5')
    rows = cursor.fetchall()
    
    # Show column names
    cursor.execute(f'PRAGMA table_info({table})')
    cols = [c[1] for c in cursor.fetchall()]
    print('Columns:', cols)
    
    if rows:
        for row in rows:
            print(row)
    else:
        print('Empty')

conn.close()