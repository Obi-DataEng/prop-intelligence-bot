import json
import re
from datetime import datetime

def parse_projections(raw_text):
    """Parse projections fullText into structured game data"""
    games = []
    
    # Split by game blocks - each game has two 'Proj Runs' entries
    lines = raw_text.strip().split('\n')
    lines = [l.strip() for l in lines if l.strip()]
    
    i = 0
    while i < len(lines):
        try:
            # Look for team abbreviation patterns followed by pitcher
            if (i + 15 < len(lines) and 
                re.match(r'^[A-Z]{2,3}$', lines[i]) and
                'LHP' in lines[i+1] or 'RHP' in lines[i+1]):
                
                game = {}
                game['home_team'] = lines[i]
                game['home_pitcher'] = lines[i+1].replace('LHP ', '').replace('RHP ', '')
                game['home_pitcher_hand'] = 'L' if 'LHP' in lines[i+1] else 'R'
                game['home_lineup'] = '✓' in lines[i+2] or 'Lineup' in lines[i+2]
                
                # Skip 'vs'
                vs_idx = i + 3
                while vs_idx < len(lines) and lines[vs_idx] != 'vs':
                    vs_idx += 1
                
                away_idx = vs_idx + 1
                game['away_team'] = lines[away_idx]
                game['away_pitcher'] = lines[away_idx+1].replace('LHP ', '').replace('RHP ', '')
                game['away_pitcher_hand'] = 'L' if 'LHP' in lines[away_idx+1] else 'R'
                game['away_lineup'] = '✓' in lines[away_idx+2] or 'Lineup' in lines[away_idx+2]
                
                games.append(game)
                i = away_idx + 3
            else:
                i += 1
        except:
            i += 1
    
    return games

def parse_projections_simple(raw_text):
    """Simpler parser using regex on full text block"""
    games = []
    
    # Split into lines and clean
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    
    i = 0
    while i < len(lines):
        try:
            # Look for team block: 3-letter code followed by pitcher line
            if (re.match(r'^[A-Z]{2,3}$', lines[i]) and 
                i + 1 < len(lines) and 
                ('LHP' in lines[i+1] or 'RHP' in lines[i+1] or 'Pitcher TBD' in lines[i+1])):
                
                home_team = lines[i]
                home_pitcher = lines[i+1]
                
                # Find 'vs' and away team
                j = i + 2
                while j < len(lines) and lines[j] != 'vs':
                    j += 1
                
                if j < len(lines) and lines[j] == 'vs':
                    away_team = lines[j+1] if j+1 < len(lines) else ''
                    away_pitcher = lines[j+2] if j+2 < len(lines) else ''
                    
                    # Find proj runs after this block
                    proj_runs = []
                    k = j + 3
                    while k < len(lines) and len(proj_runs) < 2:
                        if re.match(r'^\d+\.\d+$', lines[k]):
                            proj_runs.append(float(lines[k]))
                        k += 1
                    
                    # Find O/U line
                    ou_line = None
                    ml_home = None
                    ml_away = None
                    for k in range(i, min(i+40, len(lines))):
                        if lines[k] == 'O/U' and k+1 < len(lines):
                            ou_match = re.search(r'[OU] (\d+\.?\d*)', lines[k+1])
                            if ou_match:
                                ou_line = ou_match.group(1)
                        if lines[k] == 'ML' and k+2 < len(lines):
                            ml_home = lines[k+2] if re.match(r'^[+-]\d+$', lines[k+2]) else None
                    
                    game = {
                        'home_team': home_team,
                        'home_pitcher': home_pitcher.replace('LHP ', '').replace('RHP ', ''),
                        'home_pitcher_hand': 'L' if 'LHP' in home_pitcher else 'R',
                        'away_team': away_team,
                        'away_pitcher': away_pitcher.replace('LHP ', '').replace('RHP ', ''),
                        'away_pitcher_hand': 'L' if 'LHP' in away_pitcher else 'R',
                        'home_proj_runs': proj_runs[0] if len(proj_runs) > 0 else None,
                        'away_proj_runs': proj_runs[1] if len(proj_runs) > 1 else None,
                        'ou_line': ou_line,
                        'home_ml': ml_home,
                    }
                    
                    if re.match(r'^[A-Z]{2,3}$', away_team):
                        games.append(game)
                    
                    i = k
                    continue
        except Exception as e:
            pass
        i += 1
    
    return games

def parse_weather(rows):
    """Parse weather rows into structured data"""
    weather_data = []
    
    for row in rows:
        if not row:
            continue
        parts = row.split('\t') if '\t' in row else row.split('\n')
        parts = [p.strip() for p in parts if p.strip()]
        
        # Look for temperature pattern
        temp_match = re.search(r'(\d+)°F', row)
        precip_match = re.search(r'(\d+)%', row)
        wind_match = re.search(r'(\d+)\s*MPH', row, re.IGNORECASE)
        time_match = re.search(r'(\d+:\d+\s*(?:AM|PM))', row)
        
        if temp_match:
            weather_data.append({
                'temp': int(temp_match.group(1)),
                'precip': int(precip_match.group(1)) if precip_match else 0,
                'wind_speed': int(wind_match.group(1)) if wind_match else 0,
                'game_time': time_match.group(1) if time_match else None,
                'raw': row[:100]
            })
    
    return weather_data

def parse_pitcher_summary(rows):
    """Parse pitcher summary rows"""
    pitchers = []
    headers_found = False
    
    for row in rows:
        if not row:
            continue
        
        # Skip header rows
        if any(h in row for h in ['PITCHER', 'TEAM', 'Split', 'NAME']):
            headers_found = True
            continue
            
        parts = row.split('\t') if '\t' in row else row.split('  ')
        parts = [p.strip() for p in parts if p.strip()]
        
        if len(parts) >= 4:
            pitchers.append({
                'raw': row,
                'parts': parts
            })
    
    return pitchers

def parse_park_factors(rows):
    """Parse park factors"""
    parks = []
    
    for row in rows:
        if not row or 'PARK' in row.upper() or 'FACTOR' in row.upper():
            continue
        
        # Look for numeric factors
        numbers = re.findall(r'\d+\.?\d*', row)
        if len(numbers) >= 2:
            parks.append({
                'raw': row,
                'factors': numbers
            })
    
    return parks

def run_parser(raw_data, scrape_date):
    """Main parser function - takes raw scraped data and returns structured data"""
    print(f"\n{'='*50}")
    print(f"🔍 Parsing scraped data for {scrape_date}")
    print(f"{'='*50}\n")
    
    parsed = {}
    
    # Parse projections
    if raw_data.get('projections'):
        full_text = raw_data['projections'].get('fullText', '')
        parsed['games'] = parse_projections_simple(full_text)
        print(f"✅ Games parsed: {len(parsed['games'])}")
        for g in parsed['games'][:3]:  # Show first 3 as sample
            print(f"   {g['home_team']} vs {g['away_team']} | "
                  f"Proj: {g['home_proj_runs']} - {g['away_proj_runs']} | "
                  f"O/U: {g['ou_line']}")
    
    # Parse weather
    if raw_data.get('weather'):
        parsed['weather'] = parse_weather(raw_data['weather'].get('rows', []))
        print(f"✅ Weather entries parsed: {len(parsed['weather'])}")
    
    # Parse pitchers
    if raw_data.get('pitcher_summary'):
        parsed['pitchers'] = parse_pitcher_summary(
            raw_data['pitcher_summary'].get('rows', [])
        )
        print(f"✅ Pitcher rows parsed: {len(parsed['pitchers'])}")
    
    # Parse park factors
    if raw_data.get('park_factors'):
        parsed['park_factors'] = parse_park_factors(
            raw_data['park_factors'].get('rows', [])
        )
        print(f"✅ Park factor rows parsed: {len(parsed['park_factors'])}")
    
    # HR matchups raw - will feed directly to Claude
    if raw_data.get('hr_matchups'):
        parsed['hr_matchups_text'] = '\n'.join(
            raw_data['hr_matchups'].get('rows', [])
        )
        print(f"✅ HR matchups text ready: {len(parsed['hr_matchups_text'])} chars")
    
    # Exit velo raw - will feed directly to Claude  
    if raw_data.get('exit_velo'):
        parsed['exit_velo_text'] = '\n'.join(
            raw_data['exit_velo'].get('rows', [])
        )
        print(f"✅ Exit velo text ready: {len(parsed['exit_velo_text'])} chars")

    print(f"\n✅ Parsing complete!")
    return parsed

if __name__ == "__main__":
    # Test parser with saved raw data
    from datetime import datetime
    import os
    
    scrape_date = datetime.now().strftime("%Y-%m-%d")
    raw_data = {}
    
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
    
    parsed = run_parser(raw_data, scrape_date)