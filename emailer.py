import smtplib
import os

from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv


load_dotenv()


# ============================================================
# COLORS
# ============================================================

TIER_COLORS = {
    "Elite": "#16A36A",
    "High": "#2563EB",
    "Medium": "#64748B",
}

WNBA_COLOR = "#7C3AED"
CFB_COLOR = "#38BDF8"
NFL_COLOR = "#A78BFA"
MLB_COLOR = "#16A36A"
NRFI_COLOR = "#8B5CF6"
NBA_COLOR = "#F97316"


# ============================================================
# GENERAL HELPERS
# ============================================================

def get_top_picks(data):
    """
    Support analyzers that return either:
      top_picks
    or:
      picks
    """
    if not data:
        return []

    picks = data.get("top_picks")

    if picks is None:
        picks = data.get("picks", [])

    return picks or []


def format_odds(odds):
    if odds is None or odds == "":
        return ""

    try:
        odds = int(odds)

        if odds > 0:
            return f"+{odds}"

        return str(odds)

    except (TypeError, ValueError):
        return str(odds)


def format_line(line):
    if line is None or line == "":
        return ""

    try:
        value = float(line)

        if value > 0:
            return f"+{value:g}"

        return f"{value:g}"

    except (TypeError, ValueError):
        return str(line)


def confidence_badge(pick):
    tier = pick.get("confidence_tier", "Medium")
    confidence = pick.get(
        "prediction_confidence",
        pick.get("confidence_score", pick.get("confidence", "")),
    )
    color = TIER_COLORS.get(tier, "#64748B")
    text = f"{tier.upper()} · {confidence}" if confidence != "" else tier.upper()
    return (
        f"<span style='display:inline-block;background:{color};color:#FFFFFF;"
        f"padding:5px 9px;border-radius:999px;font-size:10px;line-height:12px;"
        f"font-weight:800;letter-spacing:.5px;'>{text}</span>"
    )


def sport_tile(count, color, label):
    return f"""
    <td width="20%" valign="top" style="padding:0 4px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
               style="background:#101C2C;border:1px solid #1E293B;border-radius:10px;">
            <tr>
                <td align="center" style="padding:12px 5px 10px;border-top:3px solid {color};border-radius:10px;">
                    <div style="font-size:21px;line-height:24px;font-weight:800;color:#F8FAFC;">{count}</div>
                    <div style="font-size:10px;line-height:15px;font-weight:700;color:#94A3B8;text-transform:uppercase;letter-spacing:.6px;">{label}</div>
                </td>
            </tr>
        </table>
    </td>
    """


# ============================================================
# WNBA SECTION
# ============================================================

def format_wnba_pick(pick):

    pick_type = (
        pick.get(
            "pick_type",
            "player_prop",
        )
        or "player_prop"
    ).lower()

    player = pick.get(
        "player_name"
    )

    category = pick.get(
        "category",
        "",
    )

    selection = pick.get(
        "selection",
        "",
    )

    game = pick.get(
        "game",
        "",
    )

    team = pick.get(
        "team",
        "",
    )

    opponent = pick.get(
        "opponent",
        "",
    )

    best_book = pick.get(
        "best_book",
        "",
    )

    best_odds = format_odds(
        pick.get(
            "best_odds"
        )
    )

    reasoning = pick.get(
        "reasoning",
        "",
    )

    factors = pick.get(
        "key_factors",
        [],
    )

    shop = pick.get(
        "line_shop_note"
    )

    # --------------------------------------------------------
    # PLAYER PROP
    # --------------------------------------------------------

    if pick_type == "player_prop":

        prop_line = pick.get(
            "prop_line",
            "",
        )

        over_under = pick.get(
            "over_under",
            "",
        )

        title = (
            f"{player or 'Player'} — "
            f"{category} "
            f"{over_under} "
            f"{prop_line}"
        )

        stats_parts = []

        season = pick.get(
            "season_avg"
        )

        l10 = pick.get(
            "l10_avg"
        )

        hit_l10 = pick.get(
            "hit_rate_l10"
        )

        if season not in (
            None,
            "",
        ):
            stats_parts.append(
                f"Season: {season}"
            )

        if l10 not in (
            None,
            "",
        ):
            stats_parts.append(
                f"L10: {l10}"
            )

        if hit_l10 not in (
            None,
            "",
        ):
            stats_parts.append(
                f"L10 Hit: {hit_l10}"
            )

        stats_html = (
            " &nbsp;|&nbsp; ".join(
                stats_parts
            )
        )

    # --------------------------------------------------------
    # GAME MARKET
    # --------------------------------------------------------

    else:

        title = (
            selection
            or category
            or "WNBA Game Pick"
        )

        stats_html = (
            f"Market: "
            f"{pick_type.replace('_', ' ').title()}"
        )

    factors_html = (
        " &bull; ".join(
            str(x)
            for x in factors[:3]
        )
        if factors
        else ""
    )

    shop_html = ""

    if shop:
        shop_html = f"""
        <div style='
            color:#F5B942;
            font-size:11px;
            margin:6px 0;
        '>
            💡 {shop}
        </div>
        """

    return f"""
    <div style='
        background:#101C2C;
        border-left:4px solid {WNBA_COLOR};
        padding:15px;
        margin:9px 0;
        border-radius:7px;
    '>

        <div style='
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:10px;
        '>

            <div style='
                color:#fff;
                font-size:15px;
                font-weight:bold;
            '>
                #{pick.get('rank', '')}
                {title}
            </div>

            {confidence_badge(pick)}

        </div>

        <div style='
            color:#94A3B8;
            font-size:12px;
            margin:6px 0;
        '>
            📅 {game}
        </div>

        <div style='
            color:#94A3B8;
            font-size:11px;
            margin:4px 0;
        '>
            {team}
            {" vs " + str(opponent) if opponent else ""}
        </div>

        <div style='
            color:{WNBA_COLOR};
            font-size:13px;
            font-weight:bold;
            margin:6px 0;
        '>
            💵 {best_book} {best_odds}
        </div>

        <div style='
            color:#94A3B8;
            font-size:11px;
            margin:5px 0;
        '>
            {stats_html}
        </div>

        {shop_html}

        <div style='
            color:#CBD5E1;
            font-size:13px;
            line-height:1.55;
            margin:8px 0;
        '>
            {reasoning}
        </div>

        <div style='
            color:#64748B;
            font-size:11px;
        '>
            {"🔑 " + factors_html if factors_html else ""}
        </div>

    </div>
    """


def format_wnba_section(
    wnba_picks,
):

    if not wnba_picks:
        return ""

    top_picks = get_top_picks(
        wnba_picks
    )

    summary = wnba_picks.get(
        "slate_summary",
        "",
    )

    best_bet = wnba_picks.get(
        "best_bet",
        "",
    )

    # --------------------------------------------------------
    # NO GAMES / NO PICKS
    # --------------------------------------------------------

    if not top_picks:

        return f"""
        <div style='
            margin:22px 0;
            border-top:3px solid {WNBA_COLOR};
            padding-top:18px;
        '>

            <h1 style='
                color:{WNBA_COLOR};
                font-size:24px;
                margin:0 0 10px;
            '>
                🏀 WNBA PICKS
            </h1>

            <div style='
                background:#101C2C;
                padding:14px;
                border-radius:8px;
                color:#94A3B8;
                font-size:13px;
            '>
                {summary or best_bet or "No qualifying WNBA bets today."}
            </div>

        </div>
        """

    picks_html = "".join(
        format_wnba_pick(pick)
        for pick in top_picks
    )

    return f"""
    <div style='
        margin:22px 0;
        border-top:3px solid {WNBA_COLOR};
        padding-top:18px;
    '>

        <h1 style='
            color:{WNBA_COLOR};
            font-size:24px;
            margin:0 0 8px;
            letter-spacing:1px;
        '>
            🏀 WNBA PICKS
        </h1>

        <p style='
            color:#94A3B8;
            font-size:13px;
            line-height:1.6;
        '>
            {summary}
        </p>

        <div style='
            background:#241526;
            border-left:4px solid {WNBA_COLOR};
            padding:14px;
            border-radius:8px;
            margin:14px 0;
        '>

            <div style='
                color:{WNBA_COLOR};
                font-size:12px;
                font-weight:bold;
                margin-bottom:5px;
            '>
                ⭐ WNBA BEST BET
            </div>

            <div style='
                color:#fff;
                font-size:14px;
            '>
                {best_bet}
            </div>

        </div>

        <h2 style='
            color:{WNBA_COLOR};
            border-bottom:1px solid #334155;
            padding-bottom:7px;
            font-size:16px;
        '>
            TODAY'S TOP WNBA PLAYS
            <span style='
                color:#64748B;
                font-size:12px;
                font-weight:normal;
            '>
                ({len(top_picks)})
            </span>
        </h2>

        {picks_html}

    </div>
    """


# ============================================================
# CFB SECTION
# ============================================================

def format_cfb_pick(pick):

    selection = pick.get(
        "selection",
        "",
    )

    pick_type = (
        pick.get(
            "pick_type",
            "",
        )
        or ""
    )

    game = pick.get(
        "game",
        "",
    )

    best_book = pick.get(
        "best_book",
        "",
    )

    best_odds = format_odds(
        pick.get(
            "best_odds"
        )
    )

    reasoning = pick.get(
        "reasoning",
        "",
    )

    team = pick.get(
        "team",
        "",
    )

    line = pick.get(
        "game_line",
        pick.get(
            "line"
        ),
    )

    over_under = pick.get(
        "over_under"
    )

    if not selection:

        if pick_type == "moneyline":
            selection = (
                f"{team} Moneyline"
            )

        elif pick_type == "spread":
            selection = (
                f"{team} "
                f"{format_line(line)}"
            )

        elif pick_type in (
            "game_total",
            "total",
        ):
            selection = (
                f"{over_under or ''} "
                f"{line or ''}"
            ).strip()

        else:
            selection = (
                "CFB Pick"
            )

    return f"""
    <div style='
        background:#101C2C;
        border-left:4px solid {CFB_COLOR};
        padding:15px;
        margin:9px 0;
        border-radius:7px;
    '>

        <div style='
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:10px;
        '>

            <div style='
                color:#fff;
                font-size:15px;
                font-weight:bold;
            '>
                #{pick.get('rank', '')}
                {selection}
            </div>

            {confidence_badge(pick)}

        </div>

        <div style='
            color:#94A3B8;
            font-size:12px;
            margin:6px 0;
        '>
            🏈 {game}
        </div>

        <div style='
            color:{CFB_COLOR};
            font-size:13px;
            font-weight:bold;
            margin:6px 0;
        '>
            💵 {best_book} {best_odds}
        </div>

        <div style='
            color:#94A3B8;
            font-size:11px;
            margin:5px 0;
        '>
            Market:
            {pick_type.replace('_', ' ').title()}
        </div>

        <div style='
            color:#CBD5E1;
            font-size:13px;
            line-height:1.55;
            margin-top:8px;
        '>
            {reasoning}
        </div>

    </div>
    """


def format_cfb_section(
    cfb_picks,
):

    if not cfb_picks:
        return ""

    combined = get_top_picks(cfb_picks)

    player_props = cfb_picks.get("player_prop_picks")
    game_picks = cfb_picks.get("game_picks")

    # Backward compatibility for older analyzer output.
    if player_props is None:
        player_props = [
            pick for pick in combined
            if pick.get("pick_type") == "player_prop"
        ]
    if game_picks is None:
        game_picks = [
            pick for pick in combined
            if pick.get("pick_type") != "player_prop"
        ]

    player_props = (player_props or [])[:5]
    game_picks = (game_picks or [])[:5]
    top_picks = player_props + game_picks

    summary = cfb_picks.get(
        "slate_summary",
        "",
    )

    games_analyzed = cfb_picks.get(
        "games_analyzed"
    )

    if not top_picks:

        if games_analyzed == 0:
            message = (
                "No CFB games scheduled today."
            )
        else:
            message = (
                summary
                or
                "No qualifying CFB bets today."
            )

        return f"""
        <div style='
            margin:22px 0;
            border-top:3px solid {CFB_COLOR};
            padding-top:18px;
        '>

            <h1 style='
                color:{CFB_COLOR};
                font-size:24px;
                margin:0 0 10px;
            '>
                🏈 CFB PICKS
            </h1>

            <div style='
                background:#101C2C;
                padding:14px;
                border-radius:8px;
                color:#94A3B8;
                font-size:13px;
            '>
                {message}
            </div>

        </div>
        """

    props_html = "".join(
        format_cfb_pick(pick)
        for pick in player_props
    ) or """
        <div style='color:#64748B;font-size:13px;padding:10px 0;'>
            No qualifying CFB player props.
        </div>
    """

    games_html = "".join(
        format_cfb_pick(pick)
        for pick in game_picks
    ) or """
        <div style='color:#64748B;font-size:13px;padding:10px 0;'>
            No qualifying CFB moneyline, spread, or total picks.
        </div>
    """

    best_prop = (
        player_props[0].get("selection", "")
        if player_props else "No qualifying player prop"
    )
    best_game = (
        game_picks[0].get("selection", "")
        if game_picks else "No qualifying game bet"
    )

    return f"""
    <div style='
        margin:22px 0;
        border-top:3px solid {CFB_COLOR};
        padding-top:18px;
    '>

        <h1 style='
            color:{CFB_COLOR};
            font-size:24px;
            margin:0 0 8px;
            letter-spacing:1px;
        '>
            🏈 CFB PICKS
        </h1>

        <p style='
            color:#94A3B8;
            font-size:13px;
            line-height:1.6;
        '>
            {summary}
        </p>

        <div style='
            background:#13212a;
            border-left:4px solid {CFB_COLOR};
            padding:14px;
            border-radius:8px;
            margin:14px 0;
        '>

            <div style='
                color:{CFB_COLOR};
                font-size:12px;
                font-weight:bold;
                margin-bottom:5px;
            '>
                ⭐ CFB BEST PLAYER PROP
            </div>

            <div style='
                color:#fff;
                font-size:14px;
            '>
                {best_prop}
            </div>

            <div style='
                color:{CFB_COLOR};
                font-size:12px;
                font-weight:bold;
                margin:12px 0 5px;
            '>
                ⭐ CFB BEST GAME BET
            </div>

            <div style='color:#fff;font-size:14px;'>
                {best_game}
            </div>

        </div>

        <h2 style='
            color:{CFB_COLOR};
            border-bottom:1px solid #334155;
            padding-bottom:7px;
            font-size:16px;
        '>
            TOP 5 CFB PLAYER PROPS
            <span style='
                color:#64748B;
                font-size:12px;
                font-weight:normal;
            '>
                ({len(player_props)})
            </span>
        </h2>

        {props_html}

        <div style='
            color:#94A3B8;
            font-size:11px;
            line-height:1.5;
            margin:8px 0 20px;
        '>
            Player-prop prices come from PropFinder. Availability may vary
            by sportsbook and jurisdiction.
        </div>

        <h2 style='
            color:{CFB_COLOR};
            border-bottom:1px solid #334155;
            padding-bottom:7px;
            font-size:16px;
        '>
            TOP 5 CFB GAME PICKS — ML / SPREAD / O-U
            <span style='
                color:#64748B;
                font-size:12px;
                font-weight:normal;
            '>
                ({len(game_picks)})
            </span>
        </h2>

        {games_html}

    </div>
    """


def format_nfl_section(nfl_picks):
    """Render NFL's separate Top 5 props and Top 5 game bets."""
    if not nfl_picks:
        return ""

    # NFL and CFB intentionally share the same two-list result schema.
    return (
        format_cfb_section(nfl_picks)
        .replace(CFB_COLOR, NFL_COLOR)
        .replace("CFB", "NFL")
    )


# ============================================================
# MLB SECTION
# ============================================================

def format_mlb_pick_row(
    pick,
):

    player = pick.get(
        "player_name",
        "N/A",
    )

    rank = pick.get(
        "rank",
        "",
    )

    tier = pick.get(
        "confidence_tier",
        "Medium",
    )

    color = TIER_COLORS.get(
        tier,
        "#94A3B8aaa",
    )

    category = pick.get(
        "category",
        "",
    )

    best_book = pick.get(
        "best_book",
        "",
    )

    best_odds = format_odds(
        pick.get(
            "best_odds"
        )
    )

    fd_odds = pick.get(
        "fd_odds"
    )

    mgm_odds = pick.get(
        "mgm_odds"
    )

    czs_odds = pick.get(
        "czs_odds"
    )

    scr_odds = pick.get(
        "scr_odds"
    )

    line = pick.get(
        "fd_line"
    )

    over_under = pick.get(
        "over_under_pick",
        "",
    )

    shop = pick.get(
        "line_shop_note"
    )

    game = pick.get(
        "game",
        "",
    )

    game_time = pick.get(
        "game_time",
        "",
    )

    reasoning = pick.get(
        "reasoning",
        "",
    )

    factors = pick.get(
        "key_factors",
        [],
    )

    book_odds = []

    if fd_odds is not None:
        book_odds.append(
            f"<span style='color:#16A36A'>"
            f"FD:{format_odds(fd_odds)}"
            f"</span>"
        )

    if mgm_odds is not None:
        book_odds.append(
            f"<span style='color:#F5B942'>"
            f"MGM:{format_odds(mgm_odds)}"
            f"</span>"
        )

    if czs_odds is not None:
        book_odds.append(
            f"<span style='color:#38BDF8'>"
            f"CZS:{format_odds(czs_odds)}"
            f"</span>"
        )

    if scr_odds is not None:
        book_odds.append(
            f"<span style='color:#ce93d8'>"
            f"SCR:{format_odds(scr_odds)}"
            f"</span>"
        )

    odds_str = (
        " &nbsp;|&nbsp; ".join(
            book_odds
        )
        if book_odds
        else "No odds"
    )

    if line is not None and over_under:
        line_display = (
            f"{over_under.upper()} "
            f"{line}"
        )

    elif line is not None:
        line_display = (
            f"Line: {line}"
        )

    elif over_under:
        line_display = (
            over_under.upper()
        )

    else:
        line_display = (
            "To Hit"
        )

    factors_html = (
        " &bull; ".join(
            str(x)
            for x in factors[:3]
        )
        if factors
        else ""
    )

    shop_html = ""

    if shop:
        shop_html = f"""
        <div style='
            background:#1a2a1a;
            border-left:3px solid #F5B942;
            padding:6px 10px;
            margin:6px 0;
            font-size:12px;
            color:#F5B942;
        '>
            💡 {shop}
        </div>
        """

    return f"""
    <div style='
        background:#101C2C;
        border-left:4px solid {color};
        padding:16px;
        margin:10px 0;
        border-radius:8px;
    '>

        <div style='
            display:flex;
            justify-content:space-between;
            align-items:center;
        '>

            <div>
                <span style='
                    color:{color};
                    font-weight:bold;
                    font-size:16px;
                '>
                    #{rank} {player}
                </span>

                <span style='
                    color:#94A3B8;
                    font-size:12px;
                    margin-left:8px;
                '>
                    — {category} | {line_display}
                </span>
            </div>

            <span style='
                background:{color};
                color:#000;
                padding:3px 9px;
                border-radius:12px;
                font-size:11px;
                font-weight:bold;
            '>
                {tier}
            </span>

        </div>

        <div style='
            color:#94A3B8;
            font-size:12px;
            margin:6px 0;
        '>
            📅 {game}
            {" | " + str(game_time) if game_time else ""}
        </div>

        <div style='
            font-size:13px;
            margin:6px 0;
        '>
            📖
            <strong style='color:{color}'>
                Best: {best_book} {best_odds}
            </strong>
            &nbsp;&nbsp;
            {odds_str}
        </div>

        {shop_html}

        <div style='
            color:#CBD5E1;
            font-size:13px;
            line-height:1.55;
            margin:8px 0;
        '>
            {reasoning}
        </div>

        <div style='
            color:#64748B;
            font-size:11px;
        '>
            {"🔑 " + factors_html if factors_html else ""}
        </div>

    </div>
    """


def format_mlb_section(
    picks_data,
):

    top_picks = picks_data.get(
        "top_picks",
        [],
    )

    summary = picks_data.get(
        "daily_summary",
        "",
    )

    best_bet = picks_data.get(
        "best_bet",
        "",
    )

    picks_html = "".join(
        format_mlb_pick_row(pick)
        for pick in top_picks
    )

    if not top_picks:
        picks_html = """
        <div style='
            color:#64748B;
            font-size:13px;
            padding:12px;
        '>
            No qualifying MLB picks today.
        </div>
        """

    return f"""
    <div style='
        margin:22px 0;
        border-top:3px solid {MLB_COLOR};
        padding-top:18px;
    '>

        <h1 style='
            color:{MLB_COLOR};
            margin:0 0 6px;
            font-size:24px;
        '>
            ⚾ MLB PICKS
        </h1>

        <p style='
            color:#94A3B8;
            font-size:13px;
            line-height:1.6;
        '>
            {summary}
        </p>

        {
            f'''
            <div style="
                background:#1a2a1a;
                border-left:4px solid {MLB_COLOR};
                padding:14px;
                border-radius:8px;
                margin:14px 0;
            ">
                <div style="
                    color:{MLB_COLOR};
                    font-size:12px;
                    font-weight:bold;
                    margin-bottom:5px;
                ">
                    ⭐ MLB BEST BET
                </div>

                <div style="
                    color:#fff;
                    font-size:14px;
                ">
                    {best_bet}
                </div>
            </div>
            '''
            if best_bet
            else ""
        }

        {picks_html}

    </div>
    """


# ============================================================
# NRFI SECTION
# ============================================================

def format_nrfi_section(
    nrfi_picks,
):

    if not nrfi_picks:
        return ""

    picks_html = ""

    for pick in nrfi_picks:

        tier = pick.get(
            "confidence_tier",
            "Medium",
        )

        color = TIER_COLORS.get(
            tier,
            "#94A3B8aaa",
        )

        bet = pick.get(
            "pick",
            "NRFI",
        )

        bet_color = (
            "#16A36A"
            if bet == "NRFI"
            else "#DC2626"
        )

        score = pick.get(
            "nrfi_score",
            "",
        )

        score_html = ""

        if score != "":
            score_html = f"""
            <span style='
                color:#38BDF8;
                font-size:12px;
                font-weight:bold;
            '>
                NRFI Score: {score}
            </span>
            """

        factors = pick.get(
            "key_factors",
            [],
        )

        factors_html = (
            " • ".join(
                str(x)
                for x in factors[:3]
            )
        )

        picks_html += f"""
        <div style='
            background:#101C2C;
            border-left:4px solid {color};
            padding:14px;
            margin:8px 0;
            border-radius:6px;
        '>

            <div style='
                display:flex;
                justify-content:space-between;
            '>

                <div>
                    <span style='
                        color:{bet_color};
                        font-weight:bold;
                        font-size:17px;
                    '>
                        {bet}
                    </span>

                    <span style='
                        color:#CBD5E1;
                        font-size:14px;
                        margin-left:8px;
                    '>
                        {pick.get('game', '')}
                    </span>
                </div>

                <span style='
                    background:{color};
                    color:#000;
                    padding:2px 8px;
                    border-radius:12px;
                    font-size:11px;
                    font-weight:bold;
                '>
                    {tier}
                </span>

            </div>

            <div style='margin:8px 0;'>
                {score_html}
            </div>

            <div style='
                color:#94A3B8;
                font-size:12px;
                margin:5px 0;
            '>
                ⚾ Away:
                {pick.get('away_pitcher', 'TBD')}
                ({pick.get('away_pitcher_nrfi_pct', '?')} NRFI)
            </div>

            <div style='
                color:#94A3B8;
                font-size:12px;
                margin:5px 0;
            '>
                🏠 Home:
                {pick.get('home_pitcher', 'TBD')}
                ({pick.get('home_pitcher_nrfi_pct', '?')} NRFI)
            </div>

            <div style='
                color:#CBD5E1;
                font-size:13px;
                line-height:1.5;
                margin:8px 0;
            '>
                {pick.get('reasoning', '')}
            </div>

            <div style='
                color:#64748B;
                font-size:11px;
            '>
                {"🔑 " + factors_html if factors_html else ""}
            </div>

        </div>
        """

    return f"""
    <div style='
        margin:20px 0;
    '>

        <h2 style='
            color:{NRFI_COLOR};
            border-bottom:2px solid {NRFI_COLOR};
            padding-bottom:8px;
            font-size:17px;
        '>
            🎰 NRFI / YRFI
            <span style='
                color:#64748B;
                font-size:12px;
                font-weight:normal;
            '>
                ({len(nrfi_picks)})
            </span>
        </h2>

        {picks_html}

    </div>
    """


# ============================================================
# NBA SECTION
# ============================================================

def format_nba_section(
    nba_picks,
):

    if not nba_picks:
        return ""

    top_picks = get_top_picks(
        nba_picks
    )

    summary = nba_picks.get(
        "slate_summary",
        "",
    )

    best_bet = nba_picks.get(
        "best_bet",
        "",
    )

    if not top_picks:

        return f"""
        <div style='
            margin:22px 0;
            border-top:3px solid {NBA_COLOR};
            padding-top:18px;
        '>

            <h1 style='
                color:{NBA_COLOR};
                margin:0 0 10px;
                font-size:24px;
            '>
                🏀 NBA PICKS
            </h1>

            <div style='
                background:#101C2C;
                padding:14px;
                border-radius:8px;
                color:#94A3B8;
                font-size:13px;
            '>
                {
                    summary
                    or best_bet
                    or "No qualifying NBA bets today."
                }
            </div>

        </div>
        """

    html = f"""
    <div style='
        margin:22px 0;
        border-top:3px solid {NBA_COLOR};
        padding-top:18px;
    '>

        <h1 style='
            color:{NBA_COLOR};
            margin:0 0 8px;
            font-size:24px;
        '>
            🏀 NBA PICKS
        </h1>

        <p style='
            color:#94A3B8;
            font-size:13px;
            line-height:1.6;
        '>
            {summary}
        </p>

        <div style='
            background:#281a15;
            border-left:4px solid {NBA_COLOR};
            padding:14px;
            border-radius:8px;
            margin:14px 0;
        '>

            <div style='
                color:{NBA_COLOR};
                font-size:12px;
                font-weight:bold;
                margin-bottom:5px;
            '>
                ⭐ NBA BEST BET
            </div>

            <div style='
                color:#fff;
                font-size:14px;
            '>
                {best_bet}
            </div>

        </div>
    """

    for pick in top_picks:

        pick_type = (
            pick.get(
                "pick_type",
                "player_prop",
            )
            or "player_prop"
        )

        player = pick.get(
            "player_name"
        )

        category = pick.get(
            "category",
            "",
        )

        selection = pick.get(
            "selection",
            "",
        )

        if pick_type == "player_prop":

            title = (
                f"{player or 'Player'} — "
                f"{category} "
                f"{pick.get('over_under', '')} "
                f"{pick.get('prop_line', '')}"
            )

        else:

            title = (
                selection
                or category
                or "NBA Pick"
            )

        html += f"""
        <div style='
            background:#101C2C;
            border-left:4px solid {NBA_COLOR};
            padding:14px;
            margin:8px 0;
            border-radius:6px;
        '>

            <div style='
                display:flex;
                justify-content:space-between;
                align-items:center;
            '>

                <div style='
                    color:#fff;
                    font-weight:bold;
                    font-size:15px;
                '>
                    #{pick.get('rank', '')}
                    {title}
                </div>

                {confidence_badge(pick)}

            </div>

            <div style='
                color:#94A3B8;
                font-size:12px;
                margin:5px 0;
            '>
                📅 {pick.get('game', '')}
            </div>

            <div style='
                color:{NBA_COLOR};
                font-size:13px;
                font-weight:bold;
                margin:5px 0;
            '>
                💵
                {pick.get('best_book', '')}
                {format_odds(pick.get('best_odds'))}
            </div>

            <div style='
                color:#CBD5E1;
                font-size:13px;
                line-height:1.5;
                margin:8px 0;
            '>
                {pick.get('reasoning', '')}
            </div>

        </div>
        """

    html += "</div>"

    return html


# ============================================================
# YESTERDAY'S RESULTS
# ============================================================

def format_daily_results(
    graded_summary,
):

    if not graded_summary:
        return ""

    rows_html = ""
    total_profit = 0

    category_emojis = {
        "HR": "💣",
        "Hit": "🎯",
        "TB": "📊",
        "K": "🔥",
        "Game": "💰",
        "Points": "🏀",
        "Rebounds": "💪",
        "Assists": "🎯",
        "Threes": "3️⃣",
        "Combo": "📊",
        "Parlay": "🎰",
        "NRFI": "🎰",
        "WNBA": "🏀",
        "CFB": "🏈",
    }

    for category, stats in graded_summary.items():

        emoji = next(
            (
                value
                for key, value
                in category_emojis.items()
                if key in category
            ),
            "📌",
        )

        wins = stats.get(
            "wins",
            0,
        )

        losses = stats.get(
            "losses",
            0,
        )

        pushes = stats.get(
            "pushes",
            0,
        )

        pending = stats.get(
            "pending",
            0,
        )

        total = (
            wins
            + losses
            + pushes
        )

        rate = (
            f"{wins / total * 100:.0f}%"
            if total > 0
            else "—"
        )

        profit = stats.get(
            "profit",
            0,
        )

        total_profit += profit

        profit_color = (
            "#16A36A"
            if profit >= 0
            else "#DC2626"
        )

        pending_text = (
            f" ({pending} pending)"
            if pending > 0
            else ""
        )

        if "NRFI" in category:

            profit_cell = """
            <td style='
                padding:8px;
                text-align:right;
                color:#64748B;
            '>
                W/L only
            </td>
            """

        else:

            profit_cell = f"""
            <td style='
                padding:8px;
                text-align:right;
                color:{profit_color};
                font-weight:bold;
            '>
                ${profit:+.2f}
            </td>
            """

        rows_html += f"""
        <tr style='
            border-bottom:1px solid #1E293B;
        '>

            <td style='
                padding:8px;
                color:#CBD5E1;
            '>
                {emoji}
                {category}
                {pending_text}
            </td>

            <td style='
                padding:8px;
                color:#fff;
                text-align:center;
            '>
                {wins}W-{losses}L-{pushes}P
            </td>

            <td style='
                padding:8px;
                color:#94A3B8;
                text-align:center;
            '>
                {rate}
            </td>

            {profit_cell}

        </tr>
        """

    total_color = (
        "#16A36A"
        if total_profit >= 0
        else "#DC2626"
    )

    return f"""
    <div style='
        margin:25px 0;
        border-top:3px solid #64748B;
        padding-top:18px;
    '>

        <h2 style='
            color:#fff;
            margin-bottom:12px;
        '>
            📊 YESTERDAY'S RESULTS
        </h2>

        <table style='
            width:100%;
            border-collapse:collapse;
        '>

            <thead>
                <tr style='
                    border-bottom:1px solid #475569;
                '>

                    <th style='
                        padding:8px;
                        color:#94A3B8;
                        text-align:left;
                        font-size:12px;
                    '>
                        Category
                    </th>

                    <th style='
                        padding:8px;
                        color:#94A3B8;
                        text-align:center;
                        font-size:12px;
                    '>
                        Record
                    </th>

                    <th style='
                        padding:8px;
                        color:#94A3B8;
                        text-align:center;
                        font-size:12px;
                    '>
                        Win%
                    </th>

                    <th style='
                        padding:8px;
                        color:#94A3B8;
                        text-align:right;
                        font-size:12px;
                    '>
                        P&L
                    </th>

                </tr>
            </thead>

            <tbody>
                {rows_html}
            </tbody>

            <tfoot>
                <tr style='
                    border-top:2px solid #475569;
                '>

                    <td
                        colspan='3'
                        style='
                            padding:10px 8px;
                            color:#fff;
                            font-weight:bold;
                        '
                    >
                        Daily Total
                    </td>

                    <td style='
                        padding:10px 8px;
                        text-align:right;
                        color:{total_color};
                        font-weight:bold;
                        font-size:16px;
                    '>
                        ${total_profit:+.2f}
                    </td>

                </tr>
            </tfoot>

        </table>

    </div>
    """


# ============================================================
# ALL-TIME PERFORMANCE
# ============================================================

def format_category_breakdown_table(
    cumulative,
    sport_prefix,
    accent_color,
):

    if not cumulative:
        return ""

    sport_categories = {
        key: value
        for key, value
        in cumulative.items()
        if key.startswith(
            sport_prefix
        )
        and key != "OVERALL"
    }

    if not sport_categories:
        return ""

    rows_html = ""

    for key, stats in sorted(
        sport_categories.items()
    ):

        label = key.replace(
            f"{sport_prefix} - ",
            "",
        )

        wins = stats.get(
            "wins",
            0,
        )

        losses = stats.get(
            "losses",
            0,
        )

        pushes = stats.get(
            "pushes",
            0,
        )

        total = (
            wins
            + losses
            + pushes
        )

        win_rate = stats.get(
            "win_rate",
            0,
        )

        profit = stats.get(
            "total_profit",
            0,
        )

        roi = stats.get(
            "roi",
            0,
        )

        rate_text = (
            f"{win_rate:.0f}%"
            if total > 0
            else "—"
        )

        profit_color = (
            "#16A36A"
            if profit >= 0
            else "#DC2626"
        )

        roi_color = (
            "#16A36A"
            if roi >= 0
            else "#DC2626"
        )

        if label == "NRFI":

            profit_cell = """
            <td style='
                padding:7px;
                text-align:right;
                color:#64748B;
                font-size:12px;
            '>
                W/L only
            </td>
            """

            roi_cell = """
            <td style='
                padding:7px;
                text-align:right;
                color:#64748B;
                font-size:12px;
            '>
                —
            </td>
            """

        else:

            profit_cell = f"""
            <td style='
                padding:7px;
                text-align:right;
                color:{profit_color};
                font-size:12px;
                font-weight:bold;
            '>
                ${profit:+.2f}
            </td>
            """

            roi_cell = f"""
            <td style='
                padding:7px;
                text-align:right;
                color:{roi_color};
                font-size:12px;
            '>
                {roi:+.1f}%
            </td>
            """

        rows_html += f"""
        <tr style='
            border-bottom:1px solid #101C2C;
        '>

            <td style='
                padding:7px;
                color:#CBD5E1;
                font-size:12px;
            '>
                {label}
            </td>

            <td style='
                padding:7px;
                color:#fff;
                text-align:center;
                font-size:12px;
            '>
                {wins}W-{losses}L-{pushes}P
            </td>

            <td style='
                padding:7px;
                color:#94A3B8;
                text-align:center;
                font-size:12px;
            '>
                {rate_text}
            </td>

            {profit_cell}
            {roi_cell}

        </tr>
        """

    return f"""
    <table style='
        width:100%;
        border-collapse:collapse;
        margin-top:8px;
    '>

        <thead>
            <tr style='
                border-bottom:2px solid {accent_color};
            '>

                <th style='
                    padding:6px;
                    color:#94A3B8;
                    text-align:left;
                    font-size:11px;
                '>
                    Category
                </th>

                <th style='
                    padding:6px;
                    color:#94A3B8;
                    text-align:center;
                    font-size:11px;
                '>
                    Record
                </th>

                <th style='
                    padding:6px;
                    color:#94A3B8;
                    text-align:center;
                    font-size:11px;
                '>
                    Win%
                </th>

                <th style='
                    padding:6px;
                    color:#94A3B8;
                    text-align:right;
                    font-size:11px;
                '>
                    P&L
                </th>

                <th style='
                    padding:6px;
                    color:#94A3B8;
                    text-align:right;
                    font-size:11px;
                '>
                    ROI
                </th>

            </tr>
        </thead>

        <tbody>
            {rows_html}
        </tbody>

    </table>
    """


def format_all_time_performance(
    cumulative,
):

    if not cumulative:
        return ""

    overall = cumulative.get(
        "OVERALL"
    )

    overall_html = ""

    if overall:

        roi = overall.get(
            "roi",
            0,
        )

        profit = overall.get(
            "total_profit",
            0,
        )

        roi_color = (
            "#16A36A"
            if roi >= 0
            else "#DC2626"
        )

        profit_color = (
            "#16A36A"
            if profit >= 0
            else "#DC2626"
        )

        overall_html = f"""
        <div style='
            background:#101C2C;
            padding:16px;
            border-radius:8px;
            border:1px solid #334155;
            margin-bottom:16px;
        '>

            <div style='
                display:flex;
                gap:12px;
                flex-wrap:wrap;
            '>

                <div style='
                    text-align:center;
                    flex:1;
                    min-width:100px;
                '>

                    <div style='
                        color:#38BDF8;
                        font-size:20px;
                        font-weight:bold;
                    '>
                        {overall.get('wins', 0)}W-
                        {overall.get('losses', 0)}L-
                        {overall.get('pushes', 0)}P
                    </div>

                    <div style='
                        color:#64748B;
                        font-size:11px;
                    '>
                        Record
                    </div>

                </div>

                <div style='
                    text-align:center;
                    flex:1;
                    min-width:100px;
                '>

                    <div style='
                        color:#F5B942;
                        font-size:20px;
                        font-weight:bold;
                    '>
                        {overall.get('win_rate', 0)}%
                    </div>

                    <div style='
                        color:#64748B;
                        font-size:11px;
                    '>
                        Win Rate
                    </div>

                </div>

                <div style='
                    text-align:center;
                    flex:1;
                    min-width:100px;
                '>

                    <div style='
                        color:{profit_color};
                        font-size:20px;
                        font-weight:bold;
                    '>
                        ${profit:+.2f}
                    </div>

                    <div style='
                        color:#64748B;
                        font-size:11px;
                    '>
                        Total P&L
                    </div>

                </div>

                <div style='
                    text-align:center;
                    flex:1;
                    min-width:100px;
                '>

                    <div style='
                        color:{roi_color};
                        font-size:20px;
                        font-weight:bold;
                    '>
                        {roi:+.1f}%
                    </div>

                    <div style='
                        color:#64748B;
                        font-size:11px;
                    '>
                        ROI
                    </div>

                </div>

            </div>

        </div>
        """

    sections = []

    sport_configs = [
        (
            "WNBA",
            WNBA_COLOR,
            "🏀 WNBA",
        ),
        (
            "CFB",
            CFB_COLOR,
            "🏈 CFB",
        ),
        (
            "NFL",
            NFL_COLOR,
            "🏈 NFL",
        ),
        (
            "MLB",
            MLB_COLOR,
            "⚾ MLB",
        ),
        (
            "NBA",
            NBA_COLOR,
            "🏀 NBA",
        ),
    ]

    for (
        prefix,
        color,
        label,
    ) in sport_configs:

        table = (
            format_category_breakdown_table(
                cumulative,
                prefix,
                color,
            )
        )

        if table:

            sections.append(
                f"""
                <div style='
                    background:#0B1625;
                    padding:14px;
                    border-radius:8px;
                    border:1px solid #334155;
                    margin-top:12px;
                '>

                    <h3 style='
                        color:{color};
                        margin:0 0 8px;
                        font-size:13px;
                    '>
                        {label} Breakdown
                    </h3>

                    {table}

                </div>
                """
            )

    return f"""
    <div style='
        margin:28px 0;
        border-top:3px solid #475569;
        padding-top:18px;
    '>

        <h2 style='
            color:#fff;
            margin-bottom:14px;
        '>
            📈 ALL-TIME PERFORMANCE
        </h2>

        {overall_html}

        {''.join(sections)}

    </div>
    """


# ============================================================
# ASSEMBLE COMPLETE EMAIL
# ============================================================

def format_picks_email(
    picks_data,
    scrape_date,
    graded_summary=None,
    cumulative=None,
    nba_picks=None,
    wnba_picks=None,
    cfb_picks=None,
    nfl_picks=None,
):
    mlb_picks = picks_data.get("top_picks", [])
    nrfi_picks = picks_data.get("nrfi_picks", [])
    wnba_top = get_top_picks(wnba_picks)
    cfb_top = get_top_picks(cfb_picks)
    nfl_top = get_top_picks(nfl_picks)
    nba_top = get_top_picks(nba_picks)

    mlb_count = len(mlb_picks)
    nrfi_count = len(nrfi_picks)
    wnba_count = len(wnba_top)
    cfb_count = len(cfb_top)
    nfl_count = len(nfl_top)
    nba_count = len(nba_top)
    total_count = (
        mlb_count + nrfi_count + wnba_count +
        cfb_count + nfl_count + nba_count
    )

    try:
        display_date = datetime.strptime(scrape_date, "%Y-%m-%d").strftime("%A · %B %d, %Y").upper()
    except Exception:
        display_date = str(scrape_date).upper()

    stats_html = f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:18px 0 6px;">
        <tr>
            {sport_tile(wnba_count, WNBA_COLOR, "WNBA")}
            {sport_tile(cfb_count, CFB_COLOR, "CFB")}
            {sport_tile(nfl_count, NFL_COLOR, "NFL")}
            {sport_tile(mlb_count, MLB_COLOR, "MLB")}
            {sport_tile(nrfi_count, NRFI_COLOR, "NRFI")}
            {sport_tile(nba_count, NBA_COLOR, "NBA")}
        </tr>
    </table>
    """

    wnba_section = format_wnba_section(wnba_picks)
    cfb_section = format_cfb_section(cfb_picks)
    nfl_section = format_nfl_section(nfl_picks)
    results_section = format_daily_results(graded_summary)
    mlb_section = format_mlb_section(picks_data)
    nrfi_section = format_nrfi_section(nrfi_picks)
    nba_section = format_nba_section(nba_picks)
    performance_section = format_all_time_performance(cumulative)

    return f"""<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="dark">
<meta name="supported-color-schemes" content="dark">
</head>
<body style="margin:0;padding:0;background:#050B14;font-family:Arial,Helvetica,sans-serif;color:#F8FAFC;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#050B14;">
<tr><td align="center" style="padding:24px 10px;">

<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
       style="max-width:640px;background:#08111F;border:1px solid #1E293B;border-radius:18px;overflow:hidden;">

<tr>
<td style="padding:32px 28px 26px;background:#0B1625;border-bottom:1px solid #1E293B;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
        <tr>
            <td>
                <div style="font-size:11px;line-height:14px;color:#38BDF8;font-weight:800;letter-spacing:2.2px;text-transform:uppercase;">PROP INTELLIGENCE</div>
                <div style="font-size:30px;line-height:36px;color:#F8FAFC;font-weight:800;margin-top:5px;">Daily Betting Report</div>
                <div style="font-size:11px;line-height:16px;color:#64748B;font-weight:700;letter-spacing:.7px;margin-top:9px;">{display_date}</div>
            </td>
            <td align="right" valign="top">
                <span style="display:inline-block;background:#102A43;border:1px solid #1D4ED8;color:#93C5FD;padding:7px 10px;border-radius:999px;font-size:10px;font-weight:800;letter-spacing:.6px;">{total_count} VALIDATED PLAYS</span>
            </td>
        </tr>
    </table>
</td>
</tr>

<tr>
<td style="padding:0 24px 28px;">
    {stats_html}
    <div style="font-size:11px;line-height:17px;color:#64748B;text-align:center;margin:8px 0 22px;">Data-driven · Market-validated · Selective</div>

    {wnba_section}
    {cfb_section}
    {nfl_section}
    {results_section}
    {mlb_section}
    {nrfi_section}
    {nba_section}
    {performance_section}
</td>
</tr>

<tr>
<td align="center" style="padding:24px 22px;background:#070E18;border-top:1px solid #1E293B;">
    <div style="font-size:11px;line-height:14px;color:#38BDF8;font-weight:800;letter-spacing:1.8px;">PROP INTELLIGENCE</div>
    <div style="font-size:11px;line-height:18px;color:#64748B;margin-top:8px;">
        WNBA {wnba_count} &nbsp;·&nbsp; CFB {cfb_count} &nbsp;·&nbsp; NFL {nfl_count} &nbsp;·&nbsp; MLB {mlb_count} &nbsp;·&nbsp; NRFI {nrfi_count} &nbsp;·&nbsp; NBA {nba_count}
    </div>
    <div style="font-size:10px;line-height:17px;color:#475569;margin-top:12px;">
        Powered by PropFinder, Claude AI and The Odds API.<br>
        For informational and entertainment purposes only. Bet responsibly.
    </div>
</td>
</tr>

</table>
</td></tr>
</table>
</body>
</html>
"""


# ============================================================
# SEND EMAIL
# ============================================================

def send_picks_email(
    picks_data,
    scrape_date,
    graded_summary=None,
    cumulative=None,
    nba_picks=None,
    wnba_picks=None,
    cfb_picks=None,
    nfl_picks=None,
):

    sender = os.getenv(
        "GMAIL_SENDER"
    )

    password = os.getenv(
        "GMAIL_APP_PASSWORD"
    )

    recipient = os.getenv(
        "GMAIL_RECIPIENT"
    )

    recipient2 = os.getenv(
        "GMAIL_RECIPIENT_2"
    )

    recipient3 = os.getenv(
        "GMAIL_RECIPIENT_3"
    )

    recipients = [
        item
        for item in [
            recipient,
            recipient2,
            recipient3,
        ]
        if item
    ]

    if not all([
        sender,
        password,
        recipient,
    ]):

        print(
            "❌ Missing email credentials "
            "in .env file"
        )

        return False

    mlb_count = len(
        picks_data.get(
            "top_picks",
            [],
        )
    )

    nrfi_count = len(
        picks_data.get(
            "nrfi_picks",
            [],
        )
    )

    wnba_count = len(
        get_top_picks(
            wnba_picks
        )
    )

    cfb_count = len(
        get_top_picks(
            cfb_picks
        )
    )

    nfl_count = len(
        get_top_picks(
            nfl_picks
        )
    )

    nba_count = len(
        get_top_picks(
            nba_picks
        )
    )

    print(
        f"\n📧 Sending picks email "
        f"to {len(recipients)} recipient(s)..."
    )

    msg = MIMEMultipart(
        "alternative"
    )

    msg["Subject"] = (
        f"🏆 Picks {scrape_date} | "
        f"WNBA:{wnba_count} "
        f"CFB:{cfb_count} "
        f"NFL:{nfl_count} "
        f"MLB:{mlb_count} "
        f"NRFI:{nrfi_count} "
        f"NBA:{nba_count}"
    )

    msg["From"] = sender

    msg["To"] = ", ".join(
        recipients
    )

    html = format_picks_email(
        picks_data,
        scrape_date,
        graded_summary,
        cumulative,
        nba_picks=nba_picks,
        wnba_picks=wnba_picks,
        cfb_picks=cfb_picks,
        nfl_picks=nfl_picks,
    )

    msg.attach(
        MIMEText(
            html,
            "html",
        )
    )

    try:

        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
        ) as server:

            server.login(
                sender,
                password,
            )

            server.sendmail(
                sender,
                recipients,
                msg.as_string(),
            )

        print(
            f"✅ Email sent successfully "
            f"to {len(recipients)} recipient(s)!"
        )

        print(
            f"   Subject: "
            f"{msg['Subject']}"
        )

        return True

    except Exception as e:

        print(
            f"❌ Email error: {e}"
        )

        return False


# ============================================================
# MANUAL EMAIL TEST
# ============================================================

if __name__ == "__main__":

    scrape_date = datetime.now().strftime("%Y-%m-%d")

    import json

    picks_data = {}
    nba_picks = None
    wnba_picks = None
    cfb_picks = None
    nfl_picks = None

    picks_file = f"logs/{scrape_date}_picks.json"
    nba_file = f"logs/{scrape_date}_nba_picks.json"
    wnba_file = f"logs/{scrape_date}_wnba_picks.json"
    cfb_file = f"logs/{scrape_date}_cfb_picks.json"
    nfl_file = f"logs/{scrape_date}_nfl_picks.json"

    # ========================================================
    # MLB / NRFI
    # ========================================================

    if os.path.exists(picks_file):

        with open(
            picks_file,
            "r",
            encoding="utf-8",
        ) as f:
            picks_data = json.load(f)

        print(f"✅ Loaded MLB picks: {picks_file}")

    else:

        print(
            f"⚠️ No MLB picks file found at {picks_file}"
        )

        print(
            "   Continuing email test without MLB picks."
        )

        picks_data = {
            "top_picks": [],
            "nrfi_picks": [],
            "daily_summary": "No MLB picks file available.",
            "best_bet": "",
        }

    # ========================================================
    # WNBA
    # ========================================================

    if os.path.exists(wnba_file):

        with open(
            wnba_file,
            "r",
            encoding="utf-8",
        ) as f:
            wnba_picks = json.load(f)

        print(f"✅ Loaded WNBA picks: {wnba_file}")

    else:

        print(
            f"⚠️ No WNBA picks file found at {wnba_file}"
        )

    # ========================================================
    # CFB
    # ========================================================

    if os.path.exists(cfb_file):

        with open(
            cfb_file,
            "r",
            encoding="utf-8",
        ) as f:
            cfb_picks = json.load(f)

        print(f"✅ Loaded CFB picks: {cfb_file}")

    else:

        print(
            f"⚠️ No CFB picks file found at {cfb_file}"
        )

    # ========================================================
    # NFL
    # ========================================================

    if os.path.exists(nfl_file):
        with open(nfl_file, "r", encoding="utf-8") as f:
            nfl_picks = json.load(f)
        print(f"✅ Loaded NFL picks: {nfl_file}")
    else:
        print(f"⚠️ No NFL picks file found at {nfl_file}")

    # ========================================================
    # NBA
    # ========================================================

    if os.path.exists(nba_file):

        with open(
            nba_file,
            "r",
            encoding="utf-8",
        ) as f:
            nba_picks = json.load(f)

        print(f"✅ Loaded NBA picks: {nba_file}")

    else:

        print(
            f"⚠️ No NBA picks file found at {nba_file}"
        )

    # ========================================================
    # GRADING
    # ========================================================

    graded_summary = None
    cumulative = None

    try:

        from grader import run_grader

        (
            graded_summary,
            cumulative,
        ) = run_grader()

        print("✅ Grading data loaded")

    except Exception as e:

        print(
            f"⚠️ Grader skipped: {e}"
        )

    # ========================================================
    # SEND TEST EMAIL
    # ========================================================

    print("\n📧 Building test email...")

    send_picks_email(
        picks_data,
        scrape_date,
        graded_summary,
        cumulative,
        nba_picks=nba_picks,
        wnba_picks=wnba_picks,
        cfb_picks=cfb_picks,
        nfl_picks=nfl_picks,
    )
