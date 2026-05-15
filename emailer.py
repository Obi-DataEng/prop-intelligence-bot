import smtplib
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TIER_COLORS = {'Elite': '#00ff88', 'High': '#ffaa00', 'Medium': '#aaaaaa'}

# ─────────────────────────────────────────────
# MLB TOP PICKS SECTION
# ─────────────────────────────────────────────

def format_top_pick_row(pick):
    player = pick.get('player_name', 'N/A')
    rank = pick.get('rank', '')
    tier = pick.get('confidence_tier', 'Medium')
    color = TIER_COLORS.get(tier, '#aaaaaa')
    cat = pick.get('category', '')
    best_book = pick.get('best_book', '')
    best_odds = pick.get('best_odds', '')
    fd_odds = pick.get('fd_odds')
    mgm_odds = pick.get('mgm_odds')
    czs_odds = pick.get('czs_odds')
    scr_odds = pick.get('scr_odds')
    line = pick.get('fd_line')
    over_under = pick.get('over_under_pick', '')
    shop = pick.get('line_shop_note')
    game = pick.get('game', '')
    game_time = pick.get('game_time', '')
    reasoning = pick.get('reasoning', '')
    factors = pick.get('key_factors', [])

    book_odds = []
    if fd_odds and str(fd_odds) != 'None': book_odds.append(f"<span style='color:#00ff88'>FD:{fd_odds}</span>")
    if mgm_odds and str(mgm_odds) != 'None': book_odds.append(f"<span style='color:#ffaa00'>MGM:{mgm_odds}</span>")
    if czs_odds and str(czs_odds) != 'None': book_odds.append(f"<span style='color:#4fc3f7'>CZS:{czs_odds}</span>")
    if scr_odds and str(scr_odds) != 'None': book_odds.append(f"<span style='color:#ce93d8'>SCR:{scr_odds}</span>")
    odds_str = ' &nbsp;|&nbsp; '.join(book_odds) if book_odds else 'No odds'

    if line and over_under:
        line_display = f"{over_under.upper()} {line}"
    elif line:
        line_display = f"Line: {line}"
    elif over_under:
        line_display = over_under.upper()
    else:
        line_display = "To Hit"

    factors_html = ' &bull; '.join(factors[:3]) if factors else ''
    shop_html = f"<div style='background:#1a2a1a;border-left:3px solid #ffaa00;padding:6px 10px;margin:6px 0;font-size:12px;color:#ffaa00;'>💡 {shop}</div>" if shop else ""

    return f"""<div style='background:#1a1a2e;border-left:4px solid {color};padding:16px;margin:10px 0;border-radius:8px;'>
        <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;'>
            <div>
                <span style='color:{color};font-weight:bold;font-size:17px;'>#{rank} {player}</span>
                <span style='color:#888;font-size:13px;margin-left:10px;'>— {cat} | {line_display}</span>
            </div>
            <span style='background:{color};color:#000;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:bold;'>{tier}</span>
        </div>
        <div style='color:#888;font-size:12px;margin:4px 0;'>📅 {game} &nbsp;|&nbsp; {game_time}</div>
        <div style='font-size:13px;margin:6px 0;'>📖 <strong style='color:{color}'>Best: {best_book} {best_odds}</strong> &nbsp;&nbsp;{odds_str}</div>
        {shop_html}
        <div style='color:#ccc;font-size:13px;margin:10px 0;line-height:1.6;'>{reasoning}</div>
        <div style='color:#666;font-size:11px;margin-top:6px;'>🔑 {factors_html}</div>
    </div>"""

def format_top_picks_section(picks):
    if not picks:
        return "<div style='margin:20px 0;'><p style='color:#555;font-style:italic;'>No top picks available today</p></div>"
    picks_html = ''.join([format_top_pick_row(p) for p in picks])
    return f"""<div style='margin:20px 0;'>
        <h2 style='color:#00ff88;border-bottom:2px solid #00ff88;padding-bottom:8px;margin-bottom:12px;'>
            ⭐ TODAY'S TOP MLB PICKS
            <span style='color:#555;font-size:14px;font-weight:normal;'> ({len(picks)} picks — odds -130 to +125 only)</span>
        </h2>
        {picks_html}
    </div>"""

# ─────────────────────────────────────────────
# NRFI SECTION
# ─────────────────────────────────────────────

def format_nrfi_section(nrfi_picks):
    if not nrfi_picks: return ""
    picks_html = ""
    for pick in nrfi_picks:
        tier = pick.get('confidence_tier', 'Medium')
        color = TIER_COLORS.get(tier, '#aaaaaa')
        bet = pick.get('pick', 'NRFI')
        bet_color = '#00ff88' if bet == 'NRFI' else '#ff4444'
        score = pick.get('nrfi_score', '')
        score_html = f"<span style='color:#4fc3f7;font-size:12px;font-weight:bold;'>NRFI Score: {score}</span>" if score else ""
        picks_html += f"""<div style='background:#1a1a2e;border-left:4px solid {color};padding:14px;margin:8px 0;border-radius:6px;'>
            <div style='display:flex;justify-content:space-between;align-items:center;'>
                <div><span style='color:{bet_color};font-weight:bold;font-size:17px;letter-spacing:1px;'>{bet}</span>
                <span style='color:#ccc;font-size:14px;margin-left:10px;'>{pick.get('game','')}</span></div>
                <span style='background:{color};color:#000;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:bold;'>{tier}</span>
            </div>
            <div style='margin:8px 0;'>{score_html}</div>
            <div style='display:flex;gap:16px;margin:4px 0;flex-wrap:wrap;'>
                <span style='color:#888;font-size:12px;'>⚾ Away: {pick.get('away_pitcher','TBD')} ({pick.get('away_pitcher_nrfi_pct','?')} NRFI, {pick.get('away_pitcher_streak','?')})</span>
                <span style='color:#888;font-size:12px;'>🏠 Home: {pick.get('home_pitcher','TBD')} ({pick.get('home_pitcher_nrfi_pct','?')} NRFI, {pick.get('home_pitcher_streak','?')})</span>
            </div>
            <div style='display:flex;gap:16px;margin:4px 0;flex-wrap:wrap;'>
                <span style='color:#666;font-size:11px;'>Away batting: {pick.get('away_team_nrfi_pct','?')} NRFI</span>
                <span style='color:#666;font-size:11px;'>Home batting: {pick.get('home_team_nrfi_pct','?')} NRFI</span>
            </div>
            <div style='color:#ccc;font-size:13px;margin:8px 0;line-height:1.5;'>{pick.get('reasoning','')}</div>
            <div style='color:#555;font-size:11px;margin-top:4px;'>🔑 {' • '.join(pick.get('key_factors',[])[:3])}</div>
            <div style='color:#444;font-size:11px;margin-top:6px;font-style:italic;'>ℹ️ Check FanDuel / DraftKings for NRFI/YRFI lines</div>
        </div>"""
    return f"<div style='margin:20px 0;'><h2 style='color:#fff;border-bottom:2px solid #9c27b0;padding-bottom:8px;margin-bottom:12px;'>🎰 NRFI / YRFI PICK <span style='color:#555;font-size:13px;font-weight:normal;'>({len(nrfi_picks)} pick — check your book for lines)</span></h2>{picks_html}</div>"

# ─────────────────────────────────────────────
# NBA SECTION
# ─────────────────────────────────────────────

def format_nba_section(nba_picks):
    if not nba_picks: return ""

    top_picks = nba_picks.get('top_picks', [])
    slate_summary = nba_picks.get('slate_summary', '')
    best_bet = nba_picks.get('best_bet', '')

    html = f"""<div style='margin:20px 0;border-top:3px solid #ff6b35;padding-top:20px;'>
        <h1 style='color:#ff6b35;margin:0 0 8px;font-size:24px;letter-spacing:2px;'>🏀 NBA PICKS</h1>
        <p style='color:#888;font-size:13px;margin:0 0 16px;line-height:1.6;'>{slate_summary}</p>
        <div style='background:#1a1a2e;padding:14px;border-radius:8px;border-left:4px solid #ff6b35;margin-bottom:20px;'>
            <p style='color:#ff6b35;font-weight:bold;margin:0 0 6px;font-size:13px;'>⭐ NBA BEST BET OF THE DAY</p>
            <p style='color:#fff;margin:0;font-size:14px;line-height:1.5;'>{best_bet}</p>
        </div>
        <h2 style='color:#ff6b35;border-bottom:1px solid #333;padding-bottom:6px;margin-bottom:12px;font-size:16px;'>
            ⭐ TODAY'S TOP NBA PICKS
            <span style='color:#555;font-size:13px;font-weight:normal;'> ({len(top_picks)} picks — odds -130 to +125 only)</span>
        </h2>"""

    for pick in top_picks:
        tier = pick.get('confidence_tier', 'Medium')
        conf_color = TIER_COLORS.get(tier, '#aaaaaa')
        player = pick.get('player_name', 'N/A')
        cat = pick.get('category', '')
        ou = pick.get('over_under', '')
        line = pick.get('prop_line', '')
        book = pick.get('best_book', '')
        odds = pick.get('best_odds', '')
        fd_odds = pick.get('fd_odds')
        mgm_odds = pick.get('mgm_odds')
        czs_odds = pick.get('czs_odds')
        game = pick.get('game', '')
        team = pick.get('team', '')
        opp = pick.get('opponent', '')
        season_avg = pick.get('season_avg', '')
        l5_avg = pick.get('l5_avg', '')
        hit_rate = pick.get('hit_rate_season', '')
        def_rank = pick.get('def_rank_vs_pos', '')
        reasoning = pick.get('reasoning', '')
        factors = pick.get('key_factors', [])
        shop = pick.get('line_shop_note')

        book_odds = []
        if fd_odds and str(fd_odds) != 'None': book_odds.append(f"<span style='color:#00ff88'>FD:{fd_odds}</span>")
        if mgm_odds and str(mgm_odds) != 'None': book_odds.append(f"<span style='color:#ffaa00'>MGM:{mgm_odds}</span>")
        if czs_odds and str(czs_odds) != 'None': book_odds.append(f"<span style='color:#4fc3f7'>CZS:{czs_odds}</span>")
        odds_str = ' &nbsp;|&nbsp; '.join(book_odds) if book_odds else ''
        shop_html = f"<div style='color:#ffaa00;font-size:11px;margin:4px 0;'>💡 {shop}</div>" if shop else ""
        factors_html = ' &bull; '.join(factors[:3]) if factors else ''

        html += f"""<div style='background:#1a1a2e;border-left:4px solid {conf_color};padding:14px;margin:8px 0;border-radius:6px;'>
            <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;'>
                <div>
                    <span style='color:{conf_color};font-size:11px;font-weight:bold;'>[{tier}]</span>
                    <span style='color:#fff;font-weight:bold;font-size:15px;'>&nbsp;{player}</span>
                    <span style='color:#4fc3f7;font-size:13px;'>&nbsp;— {cat} | {ou} {line}</span>
                </div>
                <span style='color:{conf_color};font-size:14px;font-weight:bold;'>{book} {odds}</span>
            </div>
            <div style='color:#888;font-size:12px;margin:4px 0;'>📅 {game} &nbsp;|&nbsp; {team} vs {opp}</div>
            <div style='color:#aaa;font-size:11px;margin:4px 0;'>Avg: {season_avg} &nbsp;|&nbsp; L5: {l5_avg} &nbsp;|&nbsp; Hit%: {hit_rate} &nbsp;|&nbsp; Def: {def_rank}</div>
            <div style='font-size:12px;margin:4px 0;'>{odds_str}</div>
            {shop_html}
            <div style='color:#ccc;font-size:13px;margin:8px 0;line-height:1.5;'>{reasoning}</div>
            <div style='color:#555;font-size:11px;'>🔑 {factors_html}</div>
        </div>"""

    html += "</div>"
    return html

# ─────────────────────────────────────────────
# BREAKDOWN TABLE
# ─────────────────────────────────────────────

def format_category_breakdown_table(cumulative, sport_prefix, accent_color='#00ff88'):
    sport_cats = {k: v for k, v in cumulative.items() if k.startswith(sport_prefix) and k != 'OVERALL'}
    if not sport_cats: return ""
    rows_html = ""
    for key, stats in sorted(sport_cats.items()):
        label = key.replace(f"{sport_prefix} - ", "")
        w = stats.get('wins', 0); l = stats.get('losses', 0); p = stats.get('pushes', 0)
        total = w + l + p
        win_rate = stats.get('win_rate', 0); profit = stats.get('total_profit', 0); roi = stats.get('roi', 0)
        rate_str = f"{win_rate:.0f}%" if total > 0 else "—"
        profit_color = '#00ff88' if profit >= 0 else '#ff4444'
        roi_color = '#00ff88' if roi >= 0 else '#ff4444'
        if label == 'NRFI':
            pl_cell = "<td style='padding:7px 8px;text-align:right;color:#666;font-size:12px;'>W/L only</td>"
            roi_cell = "<td style='padding:7px 8px;text-align:right;color:#666;font-size:12px;'>—</td>"
        else:
            pl_cell = f"<td style='padding:7px 8px;text-align:right;color:{profit_color};font-size:12px;font-weight:bold;'>${profit:+.2f}</td>"
            roi_cell = f"<td style='padding:7px 8px;text-align:right;color:{roi_color};font-size:12px;'>{roi:+.1f}%</td>"
        rows_html += f"<tr style='border-bottom:1px solid #1a1a2e;'><td style='padding:7px 8px;color:#ccc;font-size:12px;'>{label}</td><td style='padding:7px 8px;color:#fff;text-align:center;font-size:12px;'>{w}W-{l}L-{p}P</td><td style='padding:7px 8px;text-align:center;color:#aaa;font-size:12px;'>{rate_str}</td>{pl_cell}{roi_cell}</tr>"
    return f"<table style='width:100%;border-collapse:collapse;margin-top:8px;'><thead><tr style='border-bottom:2px solid {accent_color};'><th style='padding:6px 8px;color:#888;text-align:left;font-size:11px;'>Category</th><th style='padding:6px 8px;color:#888;text-align:center;font-size:11px;'>Record</th><th style='padding:6px 8px;color:#888;text-align:center;font-size:11px;'>Win%</th><th style='padding:6px 8px;color:#888;text-align:right;font-size:11px;'>P&L</th><th style='padding:6px 8px;color:#888;text-align:right;font-size:11px;'>ROI</th></tr></thead><tbody>{rows_html}</tbody></table>"

# ─────────────────────────────────────────────
# RESULTS SECTION
# ─────────────────────────────────────────────

def format_results_section(graded_summary, cumulative):
    if not graded_summary and not cumulative: return ""
    category_emojis = {'HR':'💣','Hit':'🎯','TB':'📊','K':'🔥','Game':'💰','Points':'🏀','Rebounds':'💪','Assists':'🎯','Threes':'3️⃣','Combo':'📊','Parlay':'🎰','NRFI':'🎰'}
    rows_html = ""
    total_profit = 0
    for cat, stats in graded_summary.items():
        emoji = next((v for k, v in category_emojis.items() if k in cat), '📌')
        w = stats.get('wins', 0); l = stats.get('losses', 0); p = stats.get('pushes', 0)
        pend = stats.get('pending', 0); total = w + l + p
        rate = f"{w/total*100:.0f}%" if total > 0 else "—"
        profit = stats.get('profit', 0); total_profit += profit
        color = '#00ff88' if profit >= 0 else '#ff4444'
        pending_str = f" ({pend} pending)" if pend > 0 else ""
        pl_cell = "<td style='padding:8px;text-align:right;color:#666;'>W/L only</td>" if 'NRFI' in cat else f"<td style='padding:8px;text-align:right;color:{color};font-weight:bold;'>${profit:+.2f}</td>"
        rows_html += f"<tr><td style='padding:8px;color:#ccc;'>{emoji} {cat}{pending_str}</td><td style='padding:8px;color:#fff;text-align:center;'>{w}W-{l}L-{p}P</td><td style='padding:8px;text-align:center;color:#aaa;'>{rate}</td>{pl_cell}</tr>"

    day_profit_color = '#00ff88' if total_profit >= 0 else '#ff4444'
    daily_table = f"<table style='width:100%;border-collapse:collapse;'><thead><tr style='border-bottom:1px solid #333;'><th style='padding:8px;color:#888;text-align:left;font-size:12px;'>Category</th><th style='padding:8px;color:#888;text-align:center;font-size:12px;'>Record</th><th style='padding:8px;color:#888;text-align:center;font-size:12px;'>Win%</th><th style='padding:8px;color:#888;text-align:right;font-size:12px;'>P&L ($5 flat)</th></tr></thead><tbody>{rows_html}</tbody><tfoot><tr style='border-top:1px solid #333;'><td colspan='3' style='padding:8px;color:#fff;font-weight:bold;'>Daily Total</td><td style='padding:8px;text-align:right;color:{day_profit_color};font-weight:bold;font-size:16px;'>${total_profit:+.2f}</td></tr></tfoot></table>"

    cumul_html = ""
    if cumulative and cumulative.get('OVERALL'):
        o = cumulative['OVERALL']
        roi_color = '#00ff88' if o['roi'] >= 0 else '#ff4444'
        pl_color = '#00ff88' if o['total_profit'] >= 0 else '#ff4444'
        cumul_html = f"<div style='background:#1a1a2e;padding:16px;border-radius:8px;border:1px solid #333;margin-top:16px;'><h3 style='color:#fff;margin:0 0 12px;font-size:14px;'>📈 OVERALL CUMULATIVE RECORD (All Time)</h3><div style='display:flex;gap:12px;flex-wrap:wrap;'><div style='text-align:center;flex:1;min-width:80px;'><div style='color:#4fc3f7;font-size:20px;font-weight:bold;'>{o['wins']}W-{o['losses']}L-{o['pushes']}P</div><div style='color:#666;font-size:11px;'>Record</div></div><div style='text-align:center;flex:1;min-width:80px;'><div style='color:#ffaa00;font-size:20px;font-weight:bold;'>{o['win_rate']}%</div><div style='color:#666;font-size:11px;'>Win Rate</div></div><div style='text-align:center;flex:1;min-width:80px;'><div style='color:{pl_color};font-size:20px;font-weight:bold;'>${o['total_profit']:+.2f}</div><div style='color:#666;font-size:11px;'>Total P&L</div></div><div style='text-align:center;flex:1;min-width:80px;'><div style='color:{roi_color};font-size:20px;font-weight:bold;'>{o['roi']:+.1f}%</div><div style='color:#666;font-size:11px;'>ROI</div></div></div></div>"

    mlb_breakdown = format_category_breakdown_table(cumulative or {}, 'MLB', '#00ff88')
    mlb_section = f"<div style='background:#111;padding:14px;border-radius:8px;border:1px solid #1e3a1e;margin-top:12px;'><h3 style='color:#00ff88;margin:0 0 8px;font-size:13px;'>⚾ MLB Breakdown (All Time)</h3>{mlb_breakdown}</div>" if mlb_breakdown else ""
    nba_breakdown = format_category_breakdown_table(cumulative or {}, 'NBA', '#ff6b35')
    nba_section = f"<div style='background:#111;padding:14px;border-radius:8px;border:1px solid #3a1e0e;margin-top:12px;'><h3 style='color:#ff6b35;margin:0 0 8px;font-size:13px;'>🏀 NBA Breakdown (All Time)</h3>{nba_breakdown}</div>" if nba_breakdown else ""

    return f"<div style='margin:20px 0;'><h2 style='color:#fff;border-bottom:2px solid #333;padding-bottom:8px;margin-bottom:12px;'>📊 YESTERDAY'S RESULTS</h2>{daily_table}{cumul_html}{mlb_section}{nba_section}</div>"

# ─────────────────────────────────────────────
# ASSEMBLE EMAIL
# ─────────────────────────────────────────────

def format_picks_email(picks_data, scrape_date, graded_summary=None, cumulative=None, nba_picks=None):
    results_section = format_results_section(graded_summary, cumulative) if graded_summary else ""
    nba_section = format_nba_section(nba_picks) if nba_picks else ""

    top_picks = picks_data.get('top_picks', [])
    nrfi_picks = picks_data.get('nrfi_picks', [])
    summary = picks_data.get('daily_summary', '')
    best_bet = picks_data.get('best_bet', '')

    mlb_count = len(top_picks)
    nrfi_count = len(nrfi_picks)
    nba_count = len(nba_picks.get('top_picks', [])) if nba_picks else 0

    def tile(count, color, label):
        return f"<div style='background:#1a1a2e;padding:10px 16px;border-radius:6px;border-top:3px solid {color};text-align:center;'><div style='color:{color};font-size:20px;font-weight:bold;'>{count}</div><div style='color:#888;font-size:11px;'>{label}</div></div>"

    stats_html = f"""<div style='display:flex;gap:10px;margin:16px 0;flex-wrap:wrap;'>
        {tile(mlb_count,'#00ff88','⚾ MLB Picks')}
        {tile(nrfi_count,'#9c27b0','🎰 NRFI') if nrfi_count > 0 else ''}
        {tile(nba_count,'#ff6b35','🏀 NBA Picks') if nba_count > 0 else ''}
    </div>"""

    return f"""<html><body style='background:#0d0d1a;color:#fff;font-family:Arial,sans-serif;padding:20px;max-width:680px;margin:0 auto;'>
        <div style='text-align:center;padding:24px 0 16px;border-bottom:2px solid #222;'>
            <h1 style='color:#00ff88;margin:0;font-size:28px;letter-spacing:2px;'>⚾🏀 MLB + NBA PICKS BOT</h1>
            <p style='color:#555;margin:6px 0 0;font-size:13px;'>{scrape_date} &nbsp;|&nbsp; FanDuel &bull; BetMGM &bull; Caesars &bull; theScore</p>
            <p style='color:#888;margin:4px 0 0;font-size:12px;'>Quality over quantity — 2 best picks per sport, odds -130 to +125</p>
        </div>
        {stats_html}
        <div style='background:#1a2a1a;border:1px solid #00ff88;padding:16px;margin:16px 0;border-radius:8px;'>
            <p style='color:#00ff88;font-weight:bold;margin:0 0 6px;font-size:13px;'>⚾ MLB BEST BET OF THE DAY</p>
            <p style='color:#fff;margin:0;font-size:15px;line-height:1.5;'>{best_bet}</p>
        </div>
        <p style='color:#aaa;font-size:13px;line-height:1.6;margin:0 0 20px;'>{summary}</p>
        {results_section}
        <div style='border-top:3px solid #00ff88;padding-top:20px;margin-top:20px;'>
            <h1 style='color:#00ff88;margin:0 0 4px;font-size:24px;letter-spacing:2px;'>⚾ MLB PICKS</h1>
        </div>
        {format_top_picks_section(top_picks)}
        {format_nrfi_section(nrfi_picks)}
        {nba_section}
        <div style='text-align:center;padding:20px 0;border-top:1px solid #222;margin-top:24px;'>
            <p style='color:#333;font-size:11px;margin:0;'>MLB + NBA Picks Bot &bull; Powered by PropFinder + Claude AI + The Odds API<br>
            MLB: {mlb_count} picks &nbsp;|&nbsp; NRFI: {nrfi_count} picks &nbsp;|&nbsp; NBA: {nba_count} picks<br><br>
            Always bet responsibly. For entertainment purposes only.</p>
        </div>
    </body></html>"""

# ─────────────────────────────────────────────
# SEND EMAIL
# ─────────────────────────────────────────────

def send_picks_email(picks_data, scrape_date, graded_summary=None, cumulative=None, nba_picks=None):
    sender = os.getenv("GMAIL_SENDER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    recipient = os.getenv("GMAIL_RECIPIENT")
    recipient2 = os.getenv("GMAIL_RECIPIENT_2")
    recipient3 = os.getenv("GMAIL_RECIPIENT_3")
    recipients = [r for r in [recipient, recipient2, recipient3] if r]

    if not all([sender, password, recipient]):
        print("❌ Missing email credentials in .env file")
        return False

    mlb_count = len(picks_data.get('top_picks', []))
    nrfi_count = len(picks_data.get('nrfi_picks', []))
    nba_count = len(nba_picks.get('top_picks', [])) if nba_picks else 0

    print(f"\n📧 Sending picks email to {len(recipients)} recipients...")
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"⚾🏀 Picks {scrape_date} | MLB:{mlb_count} 🎰{nrfi_count} NBA:{nba_count} | Top plays -130 to +125"
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)
    msg.attach(MIMEText(format_picks_email(picks_data, scrape_date, graded_summary, cumulative, nba_picks), 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
        print(f"✅ Email sent successfully to {len(recipients)} recipients!")
        print(f"   Subject: {msg['Subject']}")
        return True
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False


if __name__ == "__main__":
    from grader import run_grader
    scrape_date = datetime.now().strftime("%Y-%m-%d")
    graded_summary = None; cumulative = None
    try:
        graded_summary, cumulative = run_grader()
    except Exception as e:
        print(f"⚠️ Grader skipped: {e}")
    nba_picks = None
    nba_file = f"logs/{scrape_date}_nba_picks.json"
    if os.path.exists(nba_file):
        with open(nba_file, 'r') as f:
            nba_picks = json.load(f)
    picks_file = f"logs/{scrape_date}_picks.json"
    if os.path.exists(picks_file):
        with open(picks_file, 'r') as f:
            picks_data = json.load(f)
        send_picks_email(picks_data, scrape_date, graded_summary, cumulative, nba_picks)
    else:
        print(f"❌ No picks file found at {picks_file}")