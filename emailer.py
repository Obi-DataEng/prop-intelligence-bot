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

    picks_html = ''.join([format_pick_row(p, show_pick_type) for p in picks])

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


def format_laser_section(picks):
    """Format Laser candidates (110+ mph EV) into HTML"""
    if not picks:
        return ""

    picks_html = ""
    for pick in picks:
        tier = pick.get('confidence_tier', 'Medium')
        color = {'Elite': '#00ff88', 'High': '#ffaa00',
                 'Medium': '#aaaaaa'}.get(tier, '#aaaaaa')

        picks_html += f"""
        <div style='background:#1a1a2e;border-left:4px solid {color};
                    padding:14px;margin:8px 0;border-radius:6px;'>
            <div style='display:flex;justify-content:space-between;align-items:center;'>
                <div>
                    <span style='color:{color};font-weight:bold;font-size:15px;'>
                        #{pick.get('rank')} {pick.get('player_name')}
                    </span>
                    <span style='color:#888;font-size:12px;margin-left:8px;'>
                        {pick.get('team')} vs {pick.get('opponent')}
                    </span>
                </div>
                <span style='background:{color};color:#000;padding:2px 8px;
                             border-radius:12px;font-size:11px;font-weight:bold;'>
                    {tier}
                </span>
            </div>
            <div style='color:#888;font-size:12px;margin:6px 0;'>
                📅 {pick.get('game')} | {pick.get('game_time')}
            </div>
            <div style='display:flex;gap:16px;margin:8px 0;flex-wrap:wrap;'>
                <span style='color:#4fc3f7;font-size:12px;'>
                    🔥 Recent Max EV: {pick.get('recent_max_ev')}
                </span>
                <span style='color:#ce93d8;font-size:12px;'>
                    📊 Avg EV: {pick.get('avg_exit_velo')}
                </span>
                <span style='color:#ffaa00;font-size:12px;'>
                    💥 Barrel%: {pick.get('barrel_rate')}
                </span>
                <span style='color:#00ff88;font-size:12px;'>
                    🎯 Hard Hit%: {pick.get('hard_hit_rate')}
                </span>
            </div>
            <div style='color:#ccc;font-size:13px;margin:8px 0;line-height:1.5;'>
                {pick.get('reasoning', '')}
            </div>
            <div style='color:#666;font-size:11px;margin-top:6px;'>
                🔑 {' • '.join(pick.get('key_factors', [])[:3])}
            </div>
        </div>"""

    return f"""
    <div style='margin:20px 0;'>
        <h2 style='color:#ffffff;border-bottom:2px solid #333;
                   padding-bottom:8px;margin-bottom:12px;'>
            ⚡ LASER CANDIDATES (110+ MPH EXIT VELO)
            <span style='color:#555;font-size:13px;font-weight:normal;'>
                — Check FanDuel for odds
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


def format_results_section(graded_summary, cumulative):
    """Format yesterday's results and cumulative record for email"""
    if not graded_summary and not cumulative:
        return ""

    category_emojis = {
        'HR': '💣', 'Hit': '🎯', 'TB': '📊',
        'K': '🔥', 'Game': '💰'
    }

    rows_html = ""
    total_profit = 0

    for cat, stats in graded_summary.items():
        emoji = category_emojis.get(cat, '📌')
        w, l, p = stats['wins'], stats['losses'], stats['pushes']
        pend = stats['pending']
        total = w + l + p
        rate = f"{w/total*100:.0f}%" if total > 0 else "—"
        profit = stats['profit']
        total_profit += profit
        color = '#00ff88' if profit >= 0 else '#ff4444'
        pending_str = f" ({pend} pending)" if pend > 0 else ""

        rows_html += f"""
        <tr>
            <td style='padding:8px;color:#ccc;'>{emoji} {cat}{pending_str}</td>
            <td style='padding:8px;color:#fff;text-align:center;'>{w}W-{l}L-{p}P</td>
            <td style='padding:8px;text-align:center;color:#aaa;'>{rate}</td>
            <td style='padding:8px;text-align:right;color:{color};font-weight:bold;'>
                ${profit:+.2f}
            </td>
        </tr>"""

    cumul_html = ""
    if cumulative.get('OVERALL'):
        o = cumulative['OVERALL']
        best_cat = max(
            {k: v for k, v in cumulative.items() if k != 'OVERALL'},
            key=lambda x: cumulative[x].get('win_rate', 0),
            default=None
        )
        worst_cat = min(
            {k: v for k, v in cumulative.items() if k != 'OVERALL'},
            key=lambda x: cumulative[x].get('win_rate', 100),
            default=None
        )

        roi_color = '#00ff88' if o['roi'] >= 0 else '#ff4444'
        pl_color = '#00ff88' if o['total_profit'] >= 0 else '#ff4444'

        cumul_html = f"""
        <div style='background:#1a1a2e;padding:16px;border-radius:8px;
                    border:1px solid #333;margin-top:12px;'>
            <h3 style='color:#ffffff;margin:0 0 12px;font-size:14px;'>
                📈 CUMULATIVE RECORD
            </h3>
            <div style='display:flex;gap:12px;flex-wrap:wrap;'>
                <div style='text-align:center;flex:1;min-width:80px;'>
                    <div style='color:#4fc3f7;font-size:20px;font-weight:bold;'>
                        {o['wins']}W-{o['losses']}L
                    </div>
                    <div style='color:#666;font-size:11px;'>Record</div>
                </div>
                <div style='text-align:center;flex:1;min-width:80px;'>
                    <div style='color:#ffaa00;font-size:20px;font-weight:bold;'>
                        {o['win_rate']}%
                    </div>
                    <div style='color:#666;font-size:11px;'>Win Rate</div>
                </div>
                <div style='text-align:center;flex:1;min-width:80px;'>
                    <div style='color:{pl_color};font-size:20px;font-weight:bold;'>
                        ${o['total_profit']:+.2f}
                    </div>
                    <div style='color:#666;font-size:11px;'>Total P&L</div>
                </div>
                <div style='text-align:center;flex:1;min-width:80px;'>
                    <div style='color:{roi_color};font-size:20px;font-weight:bold;'>
                        {o['roi']:+.1f}%
                    </div>
                    <div style='color:#666;font-size:11px;'>ROI</div>
                </div>
            </div>
            {f"<div style='margin-top:10px;font-size:12px;color:#888;'>🏆 Best: {best_cat} ({cumulative[best_cat]['win_rate']}%) &nbsp;|&nbsp; ⚠️ Worst: {worst_cat} ({cumulative[worst_cat]['win_rate']}%)</div>" if best_cat and worst_cat else ""}
        </div>"""

    day_profit_color = '#00ff88' if total_profit >= 0 else '#ff4444'

    return f"""
    <div style='margin:20px 0;'>
        <h2 style='color:#ffffff;border-bottom:2px solid #333;
                   padding-bottom:8px;margin-bottom:12px;'>
            📊 YESTERDAY'S RESULTS
        </h2>
        <table style='width:100%;border-collapse:collapse;'>
            <thead>
                <tr style='border-bottom:1px solid #333;'>
                    <th style='padding:8px;color:#888;text-align:left;
                               font-size:12px;'>Category</th>
                    <th style='padding:8px;color:#888;text-align:center;
                               font-size:12px;'>Record</th>
                    <th style='padding:8px;color:#888;text-align:center;
                               font-size:12px;'>Win%</th>
                    <th style='padding:8px;color:#888;text-align:right;
                               font-size:12px;'>P&L ($5 flat)</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
            <tfoot>
                <tr style='border-top:1px solid #333;'>
                    <td colspan='3' style='padding:8px;color:#fff;
                                          font-weight:bold;'>Daily Total</td>
                    <td style='padding:8px;text-align:right;
                               color:{day_profit_color};font-weight:bold;font-size:16px;'>
                        ${total_profit:+.2f}
                    </td>
                </tr>
            </tfoot>
        </table>
        {cumul_html}
    </div>"""


def format_nba_section(nba_picks):
    """Format NBA picks into HTML section"""
    if not nba_picks:
        return ""

    categories = [
        ('points_picks',   '🏀 Points Props'),
        ('rebounds_picks', '💪 Rebounds Props'),
        ('assists_picks',  '🎯 Assists Props'),
        ('threes_picks',   '3️⃣ Threes Props'),
        ('combo_picks',    '📊 Combo Props'),
        ('game_picks',     '💰 Game Picks'),
    ]

    html = f"""
    <div style='margin:20px 0;border-top:3px solid #ff6b35;padding-top:20px;'>
        <h1 style='color:#ff6b35;margin:0 0 8px;font-size:24px;
                   letter-spacing:2px;'>🏀 NBA PICKS</h1>
        <p style='color:#888;font-size:13px;margin:0 0 16px;line-height:1.6;'>
            {nba_picks.get('slate_summary', '')}
        </p>
        <div style='background:#1a1a2e;padding:14px;border-radius:8px;
                    border-left:4px solid #ff6b35;margin-bottom:20px;'>
            <p style='color:#ff6b35;font-weight:bold;margin:0 0 6px;font-size:13px;'>
                ⭐ BEST BET OF THE DAY
            </p>
            <p style='color:#ffffff;margin:0;font-size:14px;line-height:1.5;'>
                {nba_picks.get('best_bet', '')}
            </p>
        </div>"""

    for key, label in categories:
        picks = nba_picks.get(key, [])
        if not picks:
            continue

        html += f"""
        <div style='margin:16px 0;'>
            <h2 style='color:#ff6b35;border-bottom:1px solid #333;
                       padding-bottom:6px;margin-bottom:10px;font-size:16px;'>
                {label}
                <span style='color:#555;font-size:13px;font-weight:normal;'>
                    ({len(picks)} picks)
                </span>
            </h2>"""

        for pick in picks:
            confidence = pick.get('confidence', 'Medium')
            conf_color = {
                'Elite': '#00ff88',
                'High': '#ffaa00',
                'Medium': '#aaaaaa'
            }.get(confidence, '#aaaaaa')

            if key == 'game_picks':
                html += f"""
            <div style='background:#1a1a2e;border-left:4px solid {conf_color};
                        padding:12px;margin:6px 0;border-radius:6px;'>
                <div style='display:flex;justify-content:space-between;'>
                    <div>
                        <span style='color:{conf_color};font-size:11px;
                                     font-weight:bold;'>[{confidence}]</span>
                        <span style='color:#fff;font-weight:bold;font-size:14px;'>
                            &nbsp;{pick.get('pick')} — {pick.get('pick_type')}
                        </span>
                    </div>
                    <span style='color:#4fc3f7;font-size:13px;'>
                        {pick.get('best_book')} {pick.get('line')}
                    </span>
                </div>
                <div style='color:#888;font-size:12px;margin:4px 0;'>
                    📅 {pick.get('game')}
                </div>
                <div style='color:#ccc;font-size:12px;margin-top:6px;line-height:1.5;'>
                    {pick.get('reasoning', '')[:150]}
                </div>
            </div>"""
            else:
                ou = pick.get('over_under', 'OVER')
                line = pick.get('prop_line', '')
                prop_type = pick.get('prop_type', '')
                label_extra = f" {prop_type}" if prop_type else ""
                html += f"""
            <div style='background:#1a1a2e;border-left:4px solid {conf_color};
                        padding:12px;margin:6px 0;border-radius:6px;'>
                <div style='display:flex;justify-content:space-between;
                            align-items:center;'>
                    <div>
                        <span style='color:{conf_color};font-size:11px;
                                     font-weight:bold;'>[{confidence}]</span>
                        <span style='color:#fff;font-weight:bold;font-size:14px;'>
                            &nbsp;{pick.get('player_name')}
                        </span>
                        <span style='color:#4fc3f7;font-size:13px;'>
                            &nbsp;{ou} {line}{label_extra}
                        </span>
                    </div>
                    <span style='color:#4fc3f7;font-size:13px;'>
                        {pick.get('best_book')} {pick.get('best_odds')}
                    </span>
                </div>
                <div style='color:#888;font-size:12px;margin:4px 0;'>
                    📅 {pick.get('team')} vs {pick.get('opponent')}
                    &nbsp;|&nbsp; Avg: {pick.get('season_avg')}
                    &nbsp;|&nbsp; L5: {pick.get('l5_avg')}
                    &nbsp;|&nbsp; Hit%: {pick.get('hit_rate_season')}
                    &nbsp;|&nbsp; Def: {pick.get('def_rank_vs_pos')}
                </div>
                <div style='color:#ccc;font-size:12px;margin-top:6px;line-height:1.5;'>
                    {pick.get('reasoning', '')[:150]}
                </div>
            </div>"""

        html += "</div>"

    parlay = nba_picks.get('best_parlay', {})
    if parlay:
        legs_html = "".join([
            f"<li style='color:#ccc;margin:4px 0;'>{leg}</li>"
            for leg in parlay.get('legs', [])
        ])
        html += f"""
        <div style='background:#1a1a2e;border:2px solid #ff6b35;
                    padding:16px;margin:16px 0;border-radius:8px;'>
            <h3 style='color:#ff6b35;margin:0 0 10px;'>
                🎰 NBA BEST PARLAY — Est. {parlay.get('estimated_odds')}
            </h3>
            <ul style='margin:0;padding-left:20px;'>{legs_html}</ul>
            <p style='color:#888;font-size:12px;margin:10px 0 0;'>
                {parlay.get('reasoning', '')[:200]}
            </p>
        </div>"""

    html += "</div>"
    return html


def format_picks_email(picks_data, scrape_date, graded_summary=None,
                       cumulative=None, nba_picks=None):
    """Format all picks into a complete HTML email"""

    results_section = format_results_section(graded_summary, cumulative) \
                      if graded_summary else ""
    nba_section = format_nba_section(nba_picks) if nba_picks else ""

    hr_picks = picks_data.get('hr_picks', [])
    hits_picks = picks_data.get('hits_picks', [])
    tb_picks = picks_data.get('total_bases_picks', [])
    k_picks = picks_data.get('strikeout_picks', [])
    game_picks = picks_data.get('game_picks', [])
    laser_picks = picks_data.get('laser_picks', [])
    parlay = picks_data.get('best_parlay', {})
    summary = picks_data.get('daily_summary', '')
    best_bet = picks_data.get('best_bet', '')

    mlb_total = len(hr_picks) + len(hits_picks) + len(tb_picks) + \
                len(k_picks) + len(game_picks)
    laser_count = len(laser_picks)

    nba_total = sum(len(nba_picks.get(k, [])) for k in [
        'points_picks', 'rebounds_picks', 'assists_picks',
        'threes_picks', 'combo_picks', 'game_picks'
    ]) if nba_picks else 0

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
        {('<div style="background:#1a1a2e;padding:10px 16px;border-radius:6px;'
          'border-top:3px solid #4fc3f7;text-align:center;">'
          f'<div style="color:#4fc3f7;font-size:20px;font-weight:bold;">{laser_count}</div>'
          '<div style="color:#888;font-size:11px;">⚡ Lasers</div>'
          '</div>') if laser_count > 0 else ''}
        {('<div style="background:#1a1a2e;padding:10px 16px;border-radius:6px;'
          'border-top:3px solid #ff6b35;text-align:center;">'
          f'<div style="color:#ff6b35;font-size:20px;font-weight:bold;">{nba_total}</div>'
          '<div style="color:#888;font-size:11px;">NBA Picks</div>'
          '</div>') if nba_total > 0 else ''}
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
                       letter-spacing:2px;'>⚾🏀 MLB + NBA PICKS BOT</h1>
            <p style='color:#555;margin:6px 0 0;font-size:13px;'>
                {scrape_date} &nbsp;|&nbsp;
                FanDuel &bull; BetMGM &bull; Caesars &bull; theScore
            </p>
        </div>

        <!-- Stats Bar -->
        {stats_html}

        <!-- MLB Best Bet -->
        <div style='background:#1a2a1a;border:1px solid #00ff88;
                    padding:16px;margin:16px 0;border-radius:8px;'>
            <p style='color:#00ff88;font-weight:bold;
                      margin:0 0 6px;font-size:13px;'>
                ⚾ MLB BEST BET OF THE DAY
            </p>
            <p style='color:#ffffff;margin:0;font-size:15px;
                      line-height:1.5;'>{best_bet}</p>
        </div>

        <!-- Summary -->
        <p style='color:#aaa;font-size:13px;
                  line-height:1.6;margin:0 0 20px;'>{summary}</p>

        <!-- Yesterday's Results -->
        {results_section}

        <!-- MLB Picks Sections -->
        <div style='border-top:3px solid #00ff88;padding-top:20px;margin-top:20px;'>
            <h1 style='color:#00ff88;margin:0 0 16px;font-size:24px;
                       letter-spacing:2px;'>⚾ MLB PICKS</h1>
        </div>
        {format_section("HOME RUN PICKS", "💣", hr_picks)}
        {format_section("HITS PICKS", "🎯", hits_picks)}
        {format_section("TOTAL BASES PICKS", "📊", tb_picks)}
        {format_section("STRIKEOUT PICKS", "🔥", k_picks, show_pick_type=True)}
        {format_section("GAME PICKS", "💰", game_picks)}
        {format_laser_section(laser_picks)}
        {format_parlay_section(parlay)}

        <!-- NBA Picks Section -->
        {nba_section}

        <!-- Footer -->
        <div style='text-align:center;padding:20px 0;
                    border-top:1px solid #222;margin-top:24px;'>
            <p style='color:#333;font-size:11px;margin:0;'>
                MLB + NBA Picks Bot &bull; Powered by PropFinder + Claude AI +
                The Odds API<br>
                MLB: {mlb_total} picks &nbsp;|&nbsp; NBA: {nba_total} picks<br><br>
                Always bet responsibly. For entertainment purposes only.
            </p>
        </div>

    </body>
    </html>"""

    return html


def send_picks_email(picks_data, scrape_date, graded_summary=None,
                     cumulative=None, nba_picks=None):
    """Send picks email via Gmail SMTP"""

    sender = os.getenv("GMAIL_SENDER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    recipient = os.getenv("GMAIL_RECIPIENT")
    # recipient2 = os.getenv("GMAIL_RECIPIENT_2")
    # recipient3 = os.getenv("GMAIL_RECIPIENT_3")
    recipients = [r for r in [recipient, recipient2, recipient3] if r]

    if not all([sender, password, recipient]):
        print("❌ Missing email credentials in .env file")
        return False

    hr_count = len(picks_data.get('hr_picks', []))
    hits_count = len(picks_data.get('hits_picks', []))
    tb_count = len(picks_data.get('total_bases_picks', []))
    k_count = len(picks_data.get('strikeout_picks', []))
    game_count = len(picks_data.get('game_picks', []))
    laser_count = len(picks_data.get('laser_picks', []))
    mlb_total = hr_count + hits_count + tb_count + k_count + game_count

    nba_total = sum(len(nba_picks.get(k, [])) for k in [
        'points_picks', 'rebounds_picks', 'assists_picks',
        'threes_picks', 'combo_picks', 'game_picks'
    ]) if nba_picks else 0

    print(f"\n📧 Sending picks email to {len(recipients)} recipients...")

    msg = MIMEMultipart('alternative')
    msg['Subject'] = (
        f"⚾🏀 Picks {scrape_date} | "
        f"MLB:{mlb_total} NBA:{nba_total} ⚡{laser_count} | "
        f"💣{hr_count} 🎯{hits_count} 📊{tb_count} 🔥{k_count} 💰{game_count}"
    )
    msg['From'] = sender
    msg['To'] = recipient

    html_content = format_picks_email(
        picks_data, scrape_date, graded_summary, cumulative, nba_picks
    )
    msg.attach(MIMEText(html_content, 'html'))

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
    picks_file = f"logs/{scrape_date}_picks.json"
    nba_picks_file = f"logs/{scrape_date}_nba_picks.json"

    graded_summary = None
    cumulative = None
    try:
        graded_summary, cumulative = run_grader()
    except Exception as e:
        print(f"⚠️ Grader skipped: {e}")

    nba_picks = None
    if os.path.exists(nba_picks_file):
        with open(nba_picks_file, 'r') as f:
            nba_picks = json.load(f)
        print(f"📂 Loaded NBA picks")

    if os.path.exists(picks_file):
        with open(picks_file, 'r') as f:
            picks_data = json.load(f)
        send_picks_email(picks_data, scrape_date, graded_summary,
                         cumulative, nba_picks)
    else:
        print(f"❌ No picks file found at {picks_file}")
        print(f"   Run analyzer.py first")