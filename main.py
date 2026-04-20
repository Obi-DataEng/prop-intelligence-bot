import smtplib
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def format_pick_row(pick, show_pick_type=False):
    """Format a single pick into HTML"""
    tier_colors = {
        'Elite': '#00ff88',
        'High': '#ffaa00',
        'Medium': '#aaaaaa'
    }

    player = pick.get('player_name') or pick.get('pick', 'Game Pick')
    rank = pick.get('rank', '')
    tier = pick.get('confidence_tier', 'Medium')
    color = tier_colors.get(tier, '#aaaaaa')
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
    reasoning = pick.get('reasoning', '')
    factors = pick.get('key_factors', [])

    # Build odds comparison
    book_odds = []
    if fd_odds and str(fd_odds) != 'None':
        book_odds.append(f"<span style='color:#00ff88'>FD:{fd_odds}</span>")
    if mgm_odds and str(mgm_odds) != 'None':
        book_odds.append(f"<span style='color:#ffaa00'>MGM:{mgm_odds}</span>")
    if czs_odds and str(czs_odds) != 'None':
        book_odds.append(f"<span style='color:#4fc3f7'>CZS:{czs_odds}</span>")
    if scr_odds and str(scr_odds) != 'None':
        book_odds.append(f"<span style='color:#ce93d8'>SCR:{scr_odds}</span>")

    odds_str = ' &nbsp;|&nbsp; '.join(book_odds) if book_odds else 'No odds'

    # Format line
    if line and over_under:
        line_display = f"{over_under.upper()} {line}"
    elif line:
        line_display = f"Line: {line}"
    elif over_under:
        line_display = over_under.upper()
    else:
        line_display = "To Hit"

    type_label = f" <span style='color:#888;font-size:11px'>[{pick_type}]</span>" \
                 if show_pick_type and pick_type else ""
    prop_label = f"{prop_cat} " if prop_cat else ""
    factors_html = ' &bull; '.join(factors[:3]) if factors else ''

    shop_html = f"""
        <div style='background:#1a2a1a;border-left:3px solid #ffaa00;
                    padding:6px 10px;margin:6px 0;font-size:12px;color:#ffaa00;'>
            💡 {shop}
        </div>""" if shop else ""

    return f"""
    <div style='background:#1a1a2e;border-left:4px solid {color};
                padding:14px;margin:8px 0;border-radius:6px;'>
        <div style='display:flex;justify-content:space-between;align-items:center;'>
            <div>
                <span style='color:{color};font-weight:bold;font-size:15px;'>
                    #{rank} {player}{type_label}
                </span>
                <span style='color:#888;font-size:13px;margin-left:8px;'>
                    — {prop_label}{line_display}
                </span>
            </div>
            <span style='background:{color};color:#000;padding:2px 8px;
                         border-radius:12px;font-size:11px;font-weight:bold;'>
                {tier}
            </span>
        </div>
        <div style='color:#888;font-size:12px;margin:4px 0;'>
            📅 {game} &nbsp;|&nbsp; {game_time}
        </div>
        <div style='font-size:12px;margin:6px 0;'>
            📖 <strong style='color:{color}'>Best: {best_book}</strong>
            &nbsp;&nbsp;{odds_str}
        </div>
        {shop_html}
        <div style='color:#ccc;font-size:13px;margin:8px 0;line-height:1.5;'>
            {reasoning}
        </div>
        <div style='color:#666;font-size:11px;margin-top:6px;'>
            🔑 {factors_html}
        </div>
    </div>"""

def format_section(title, emoji, picks, show_pick_type=False):
    """Format a full picks section into HTML"""
    if not picks:
        return f"""
        <div style='margin:20px 0;'>
            <h2 style='color:#ffffff;border-bottom:2px solid #333;
                       padding-bottom:8px;margin-bottom:12px;'>
                {emoji} {title}
            </h2>
            <p style='color:#555;font-style:italic;'>
                No picks available for this category today
            </p>
        </div>"""

    picks_html = ''.join([
        format_pick_row(p, show_pick_type) for p in picks
    ])

    return f"""
    <div style='margin:20px 0;'>
        <h2 style='color:#ffffff;border-bottom:2px solid #333;
                   padding-bottom:8px;margin-bottom:12px;'>
            {emoji} {title}
            <span style='color:#555;font-size:14px;font-weight:normal;'>
                ({len(picks)} picks)
            </span>
        </h2>
        {picks_html}
    </div>"""

def format_parlay_section(parlay):
    """Format the best parlay into HTML"""
    if not parlay or not parlay.get('legs'):
        return ""

    legs_html = ''.join([
        f"<li style='margin:4px 0;color:#ccc;'>{leg}</li>"
        for leg in parlay.get('legs', [])
    ])

    return f"""
    <div style='background:#1a1a2e;border:2px solid #ffaa00;
                padding:16px;margin:20px 0;border-radius:8px;'>
        <h2 style='color:#ffaa00;margin:0 0 12px 0;'>🎰 BEST PARLAY</h2>
        <ul style='margin:0;padding-left:20px;'>
            {legs_html}
        </ul>
        <div style='margin-top:10px;'>
            <span style='color:#ffaa00;font-weight:bold;'>
                Est. Odds: {parlay.get('estimated_odds', 'N/A')}
            </span>
        </div>
        <div style='color:#aaa;font-size:13px;margin-top:8px;'>
            {parlay.get('reasoning', '')}
        </div>
    </div>"""

def format_picks_email(picks_data, scrape_date):
    """Format all picks into a complete HTML email"""

    hr_picks = picks_data.get('hr_picks', [])
    hits_picks = picks_data.get('hits_picks', [])
    tb_picks = picks_data.get('total_bases_picks', [])
    k_picks = picks_data.get('strikeout_picks', [])
    game_picks = picks_data.get('game_picks', [])
    parlay = picks_data.get('best_parlay', {})
    summary = picks_data.get('daily_summary', '')
    best_bet = picks_data.get('best_bet', '')

    total = len(hr_picks) + len(hits_picks) + len(tb_picks) + \
            len(k_picks) + len(game_picks)

    # Stats bar
    stats_html = f"""
    <div style='display:flex;gap:10px;margin:16px 0;flex-wrap:wrap;'>
        <div style='background:#1a1a2e;padding:10px 16px;border-radius:6px;
                    border-top:3px solid #00ff88;text-align:center;'>
            <div style='color:#00ff88;font-size:20px;font-weight:bold;'>
                {len(hr_picks)}
            </div>
            <div style='color:#888;font-size:11px;'>HR Picks</div>
        </div>
        <div style='background:#1a1a2e;padding:10px 16px;border-radius:6px;
                    border-top:3px solid #4fc3f7;text-align:center;'>
            <div style='color:#4fc3f7;font-size:20px;font-weight:bold;'>
                {len(hits_picks)}
            </div>
            <div style='color:#888;font-size:11px;'>Hits Picks</div>
        </div>
        <div style='background:#1a1a2e;padding:10px 16px;border-radius:6px;
                    border-top:3px solid #ce93d8;text-align:center;'>
            <div style='color:#ce93d8;font-size:20px;font-weight:bold;'>
                {len(tb_picks)}
            </div>
            <div style='color:#888;font-size:11px;'>TB Picks</div>
        </div>
        <div style='background:#1a1a2e;padding:10px 16px;border-radius:6px;
                    border-top:3px solid #ff7043;text-align:center;'>
            <div style='color:#ff7043;font-size:20px;font-weight:bold;'>
                {len(k_picks)}
            </div>
            <div style='color:#888;font-size:11px;'>K Picks</div>
        </div>
        <div style='background:#1a1a2e;padding:10px 16px;border-radius:6px;
                    border-top:3px solid #ffaa00;text-align:center;'>
            <div style='color:#ffaa00;font-size:20px;font-weight:bold;'>
                {len(game_picks)}
            </div>
            <div style='color:#888;font-size:11px;'>Game Picks</div>
        </div>
    </div>"""

    html = f"""
    <html>
    <body style='background:#0d0d1a;color:#ffffff;
                 font-family:Arial,sans-serif;padding:20px;
                 max-width:680px;margin:0 auto;'>

        <!-- Header -->
        <div style='text-align:center;padding:24px 0 16px;
                    border-bottom:2px solid #222;'>
            <h1 style='color:#00ff88;margin:0;font-size:28px;
                       letter-spacing:2px;'>⚾ MLB PICKS BOT</h1>
            <p style='color:#555;margin:6px 0 0;font-size:13px;'>
                {scrape_date} &nbsp;|&nbsp; 
                FanDuel &bull; BetMGM &bull; Caesars &bull; theScore
            </p>
        </div>

        <!-- Stats Bar -->
        {stats_html}

        <!-- Best Bet -->
        <div style='background:#1a2a1a;border:1px solid #00ff88;
                    padding:16px;margin:16px 0;border-radius:8px;'>
            <p style='color:#00ff88;font-weight:bold;
                      margin:0 0 6px;font-size:13px;'>
                🎯 BEST BET OF THE DAY
            </p>
            <p style='color:#ffffff;margin:0;font-size:15px;
                      line-height:1.5;'>{best_bet}</p>
        </div>

        <!-- Summary -->
        <p style='color:#aaa;font-size:13px;
                  line-height:1.6;margin:0 0 20px;'>{summary}</p>

        <!-- Picks Sections -->
        {format_section("HOME RUN PICKS", "💣", hr_picks)}
        {format_section("HITS PICKS", "🎯", hits_picks)}
        {format_section("TOTAL BASES PICKS", "📊", tb_picks)}
        {format_section("STRIKEOUT PICKS", "🔥", k_picks, show_pick_type=True)}
        {format_section("GAME PICKS", "💰", game_picks)}

        <!-- Best Parlay -->
        {format_parlay_section(parlay)}

        <!-- Footer -->
        <div style='text-align:center;padding:20px 0;
                    border-top:1px solid #222;margin-top:24px;'>
            <p style='color:#333;font-size:11px;margin:0;'>
                MLB Picks Bot &bull; Powered by PropFinder + Claude AI +
                The Odds API<br>
                {total} total picks generated today<br><br>
                Always bet responsibly. For entertainment purposes only.
            </p>
        </div>

    </body>
    </html>"""

    return html

def send_picks_email(picks_data, scrape_date):
    """Send picks email via Gmail SMTP"""

    sender = os.getenv("GMAIL_SENDER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    recipient = os.getenv("GMAIL_RECIPIENT")

    if not all([sender, password, recipient]):
        print("❌ Missing email credentials in .env file")
        return False

    hr_count = len(picks_data.get('hr_picks', []))
    hits_count = len(picks_data.get('hits_picks', []))
    tb_count = len(picks_data.get('total_bases_picks', []))
    k_count = len(picks_data.get('strikeout_picks', []))
    game_count = len(picks_data.get('game_picks', []))
    total = hr_count + hits_count + tb_count + k_count + game_count

    print(f"\n📧 Sending picks email to {recipient}...")

    msg = MIMEMultipart('alternative')
    msg['Subject'] = (
        f"⚾ MLB Picks {scrape_date} | "
        f"{total} Picks | "
        f"💣{hr_count} 🎯{hits_count} 📊{tb_count} 🔥{k_count} 💰{game_count}"
    )
    msg['From'] = sender
    msg['To'] = recipient

    html_content = format_picks_email(picks_data, scrape_date)
    msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        print(f"✅ Email sent successfully!")
        print(f"   Subject: {msg['Subject']}")
        return True
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False

if __name__ == "__main__":
    scrape_date = datetime.now().strftime("%Y-%m-%d")
    picks_file = f"logs/{scrape_date}_picks.json"

    if os.path.exists(picks_file):
        with open(picks_file, 'r') as f:
            picks_data = json.load(f)
        send_picks_email(picks_data, scrape_date)
    else:
        print(f"❌ No picks file found at {picks_file}")
        print(f"   Run analyzer.py first")