import asyncio
import inspect
import json
import os

from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv


load_dotenv()


# ============================================================
# GLOBAL SETTINGS
# ============================================================

EASTERN = ZoneInfo("America/New_York")


# ============================================================
# DATE / ODDS HELPERS
# ============================================================

def get_eastern_now():
    return datetime.now(EASTERN)


def parse_commence_time(value):
    """
    Parse The Odds API UTC timestamps such as:
    2026-08-30T02:00:00Z
    """
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None


def game_is_on_date(game, scrape_date):
    """
    Return True only when the game occurs on scrape_date
    in America/New_York time.
    """
    commence = parse_commence_time(
        game.get("commence_time")
    )

    if commence is None:
        return False

    try:
        target_date = datetime.strptime(
            scrape_date,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return False

    eastern_game_time = commence.astimezone(
        EASTERN
    )

    return eastern_game_time.date() == target_date


def filter_daily_odds_data(
    odds_data,
    scrape_date,
):
    """
    Filter NBA/WNBA odds to ONLY games occurring on
    scrape_date in Eastern Time.

    Also removes player props belonging to games outside
    today's slate.
    """
    if not isinstance(odds_data, dict):
        return {}

    filtered = dict(odds_data)

    all_games = odds_data.get(
        "games",
        [],
    )

    daily_games = [
        game
        for game in all_games
        if game_is_on_date(
            game,
            scrape_date,
        )
    ]

    filtered["games"] = daily_games

    # --------------------------------------------------------
    # Filter player props to today's games.
    #
    # Current odds_fetcher structure uses keys like:
    # "Away Team@Home Team"
    # --------------------------------------------------------
    player_props = odds_data.get(
        "player_props",
        {},
    )

    if isinstance(player_props, dict):

        valid_game_keys = set()

        for game in daily_games:
            away = game.get(
                "away_team",
                "",
            )
            home = game.get(
                "home_team",
                "",
            )

            if away and home:
                valid_game_keys.add(
                    f"{away}@{home}"
                )

        filtered["player_props"] = {
            game_key: props
            for game_key, props
            in player_props.items()
            if game_key in valid_game_keys
        }

    return filtered


def load_json_file(
    filepath,
    default=None,
):
    if default is None:
        default = {}

    if not os.path.exists(filepath):
        return default

    with open(
        filepath,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


# ============================================================
# MAIN DAILY PIPELINE
# ============================================================

async def run_all():

    now = get_eastern_now()

    scrape_date = now.strftime(
        "%Y-%m-%d"
    )

    start_time = now

    print(
        f"\n{'=' * 65}"
    )
    print(
        f"🏆 DAILY SPORTS PICKS BOT — {scrape_date}"
    )
    print(
        f"⏰ Started at "
        f"{start_time.strftime('%I:%M %p')} ET"
    )
    print(
        f"{'=' * 65}\n"
    )

    os.makedirs(
        "logs",
        exist_ok=True,
    )

    os.makedirs(
        "data",
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Initialize grading database
    # --------------------------------------------------------

    try:
        from grader import init_db

        init_db()

    except Exception as e:
        print(
            f"⚠️ Database initialization failed: {e}"
        )

    # ========================================================
    # MLB
    # ========================================================

    print(
        "\n"
        + "=" * 65
    )
    print(
        "⚾ MLB PIPELINE"
    )
    print(
        "=" * 65
        + "\n"
    )

    # --------------------------------------------------------
    # STEP 1 — MLB PROPFINDER
    # --------------------------------------------------------

    print(
        "📡 STEP 1 — Scraping PropFinder (MLB)..."
    )

    try:
        from scraper import run_scraper

        await run_scraper()

        print(
            "✅ Step 1 complete\n"
        )

    except Exception as e:
        print(
            f"❌ MLB scraper failed: {e}"
        )
        print(
            "⚠️ Continuing without fresh "
            "PropFinder MLB data...\n"
        )

    # --------------------------------------------------------
    # STEP 1.5 — NRFI
    # --------------------------------------------------------

    print(
        "🎰 STEP 1.5 — Scraping NRFI/YRFI data..."
    )

    nrfi_data = None

    try:
        from scraper import run_nrfi_scraper

        nrfi_data = await run_nrfi_scraper(
            scrape_date
        )

        total_matchups = len(
            nrfi_data.get(
                "matchups",
                [],
            )
        )

        print(
            f"✅ Step 1.5 complete — "
            f"{total_matchups} matchup cards\n"
        )

    except Exception as e:
        print(
            f"⚠️ NRFI scraper failed "
            f"(skipping): {e}\n"
        )

    # --------------------------------------------------------
    # STEP 2 — MLB ODDS
    # --------------------------------------------------------

    print(
        "💰 STEP 2 — Fetching MLB odds..."
    )

    odds_data = {}

    try:
        from odds_fetcher import fetch_all_odds

        fetch_all_odds()

        odds_file = (
            f"logs/{scrape_date}_odds.json"
        )

        odds_data = load_json_file(
            odds_file,
            {},
        )

        print(
            "✅ Step 2 complete\n"
        )

    except Exception as e:
        print(
            f"❌ MLB odds fetcher failed: {e}"
        )
        print(
            "⚠️ Continuing without fresh odds...\n"
        )

    # --------------------------------------------------------
    # STEP 2.5 — MLB NEWS
    # --------------------------------------------------------

    print(
        "📰 STEP 2.5 — Fetching MLB news..."
    )

    try:
        from news_fetcher import fetch_mlb_news

        fetch_mlb_news(
            odds_data.get(
                "games",
                [],
            ),
            scrape_date,
        )

        print(
            "✅ Step 2.5 complete\n"
        )

    except Exception as e:
        print(
            f"⚠️ MLB news failed "
            f"(skipping): {e}\n"
        )

    # --------------------------------------------------------
    # STEP 3 — MLB ANALYSIS
    # --------------------------------------------------------

    print(
        "🧠 STEP 3 — Generating MLB picks "
        "with Claude..."
    )

    picks = None

    try:
        from parser import run_parser
        from analyzer import (
            load_odds,
            analyze_and_generate_picks,
        )

        raw_data = {}

        mlb_tabs = [
            "hr_matchups",
            "exit_velo",
            "pitcher_summary",
            "park_factors",
            "weather",
            "projections",
        ]

        for tab in mlb_tabs:

            filepath = (
                f"logs/"
                f"{scrape_date}_{tab}.json"
            )

            if os.path.exists(filepath):

                with open(
                    filepath,
                    "r",
                    encoding="utf-8",
                ) as f:
                    raw_data[tab] = json.load(f)

                print(
                    f"   📂 Loaded {tab}"
                )

            else:
                print(
                    f"   ⚠️ Missing {filepath}"
                )

        parsed = run_parser(
            raw_data,
            scrape_date,
        )

        odds_data = load_odds(
            scrape_date
        )

        picks = analyze_and_generate_picks(
            parsed,
            odds_data,
            scrape_date,
        )

        if picks:

            output_file = (
                f"logs/"
                f"{scrape_date}_picks.json"
            )

            with open(
                output_file,
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(
                    picks,
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

            pick_count = len(
                picks.get(
                    "top_picks",
                    [],
                )
            )

            print(
                f"✅ Step 3 complete — "
                f"{pick_count} MLB picks saved\n"
            )

        else:
            print(
                "⚠️ No MLB picks generated\n"
            )

    except Exception as e:
        print(
            f"❌ MLB analyzer failed: {e}"
        )

        import traceback
        traceback.print_exc()

    # --------------------------------------------------------
    # STEP 3.2 — NRFI ANALYSIS
    # --------------------------------------------------------

    print(
        "🎰 STEP 3.2 — Generating NRFI picks "
        "with Claude..."
    )

    nrfi_picks = None

    try:

        if not nrfi_data:

            nrfi_file = (
                f"logs/"
                f"{scrape_date}_nrfi.json"
            )

            nrfi_data = load_json_file(
                nrfi_file,
                None,
            )

        if nrfi_data:

            import anthropic

            from analyzer import (
                generate_nrfi_picks,
            )

            client = anthropic.Anthropic(
                api_key=os.getenv(
                    "ANTHROPIC_API_KEY"
                )
            )

            nrfi_picks = generate_nrfi_picks(
                nrfi_data,
                scrape_date,
                client,
            )

            if picks is not None:

                picks[
                    "nrfi_picks"
                ] = nrfi_picks or []

                output_file = (
                    f"logs/"
                    f"{scrape_date}_picks.json"
                )

                with open(
                    output_file,
                    "w",
                    encoding="utf-8",
                ) as f:
                    json.dump(
                        picks,
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )

            print(
                f"✅ Step 3.2 complete — "
                f"{len(nrfi_picks) if nrfi_picks else 0} "
                f"NRFI pick(s)\n"
            )

        else:
            print(
                "⚠️ No NRFI data available, skipping\n"
            )

    except Exception as e:
        print(
            f"⚠️ NRFI analyzer failed "
            f"(skipping): {e}\n"
        )

        import traceback
        traceback.print_exc()

    # ========================================================
    # GRADING
    # ========================================================

    print(
        "\n📊 STEP 3.5 — Grading yesterday's picks..."
    )

    graded_summary = None
    cumulative = None

    try:
        from grader import run_grader

        (
            graded_summary,
            cumulative,
        ) = run_grader()

        print(
            "✅ Step 3.5 complete\n"
        )

    except Exception as e:
        print(
            f"⚠️ Grader failed "
            f"(skipping): {e}\n"
        )

    # ========================================================
    # WNBA
    # ========================================================

    print(
        "\n"
        + "=" * 65
    )
    print(
        "🏀 WNBA PIPELINE"
    )
    print(
        "=" * 65
        + "\n"
    )

    wnba_odds = {}
    wnba_picks = None

    # --------------------------------------------------------
    # STEP 4 — WNBA ODDS FIRST
    # --------------------------------------------------------

    print(
        "🏀 STEP 4 — Fetching WNBA odds..."
    )

    try:
        from odds_fetcher import fetch_wnba_odds

        raw_wnba_odds = fetch_wnba_odds()

        if not raw_wnba_odds:

            raw_wnba_odds = load_json_file(
                f"logs/"
                f"{scrape_date}_wnba_odds.json",
                {},
            )

        wnba_odds = filter_daily_odds_data(
            raw_wnba_odds,
            scrape_date,
        )

        raw_count = len(
            raw_wnba_odds.get(
                "games",
                [],
            )
        )

        today_count = len(
            wnba_odds.get(
                "games",
                [],
            )
        )

        print(
            f"   📥 WNBA games from API: "
            f"{raw_count}"
        )

        print(
            f"   📅 WNBA games on "
            f"{scrape_date}: "
            f"{today_count}"
        )

        print(
            "✅ Step 4 complete\n"
        )

    except Exception as e:
        print(
            f"⚠️ WNBA odds failed "
            f"(skipping): {e}\n"
        )

        wnba_odds = {}

    # --------------------------------------------------------
    # Only run expensive WNBA work when games exist today
    # --------------------------------------------------------

    wnba_game_count = len(
        wnba_odds.get(
            "games",
            [],
        )
    )

    if wnba_game_count > 0:

         # ----------------------------------------------------
        # STEP 4.1 — WNBA PROPFINDER
        # ----------------------------------------------------

        print(
            "\n🏀 STEP 4.1 — Scraping WNBA PropFinder data...",
            flush=True,
        )

        try:
            from scraper import run_wnba_scraper

            WNBA_SCRAPER_TIMEOUT = 360  # 6 minutes maximum

            await asyncio.wait_for(
                run_wnba_scraper(),
                timeout=WNBA_SCRAPER_TIMEOUT,
            )

            print(
                "✅ Step 4.1 complete",
                flush=True,
            )

        except asyncio.TimeoutError:
            print(
                "\n⏰ WNBA PropFinder exceeded 6 minutes.",
                flush=True,
            )

            print(
                "⚠️ Stopping WNBA scrape and continuing bot.",
                flush=True,
            )

        except Exception as e:
            print(
                f"\n⚠️ WNBA PropFinder failed: {e}",
                flush=True,
            )

            print(
                "➡️ Continuing with remaining pipelines.",
                flush=True,
            )

        # ----------------------------------------------------
        # STEP 4.2 — WNBA NEWS
        # ----------------------------------------------------

        print(
            "📰 STEP 4.2 — Fetching WNBA news..."
        )

        try:
            from news_fetcher import (
                fetch_wnba_news,
            )

            fetch_wnba_news(
                wnba_odds.get(
                    "games",
                    [],
                ),
                scrape_date,
            )

            print(
                "✅ Step 4.2 complete\n"
            )

        except Exception as e:
            print(
                f"⚠️ WNBA news failed "
                f"(continuing): {e}\n"
            )

        # ----------------------------------------------------
        # STEP 4.3 — WNBA ANALYSIS
        # ----------------------------------------------------

        print(
            "🧠 STEP 4.3 — Generating WNBA picks..."
        )

        try:
            from wnba_analyzer import (
                run_wnba_analyzer,
            )

            wnba_picks = run_wnba_analyzer(
                scrape_date,
                wnba_odds,
            )

            wnba_count = len(
                wnba_picks.get(
                    "top_picks",
                    [],
                )
            ) if wnba_picks else 0

            print(
                f"✅ Step 4.3 complete — "
                f"{wnba_count} WNBA pick(s)\n"
            )

        except Exception as e:
            print(
                f"⚠️ WNBA analyzer failed "
                f"(skipping): {e}\n"
            )

            import traceback
            traceback.print_exc()

    else:

        print(
            f"ℹ️ No WNBA games scheduled for "
            f"{scrape_date}."
        )

        print(
            "   Skipping WNBA PropFinder, news, "
            "and Claude analysis.\n"
        )

        wnba_picks = {
            "league": "WNBA",
            "top_picks": [],
            "picks": [],
            "best_bet": (
                "No WNBA games scheduled today."
            ),
            "slate_summary": (
                "No WNBA games scheduled today."
            ),
        }

    # ========================================================
    # CFB
    # ========================================================

    print(
        "\n"
        + "=" * 65
    )
    print(
        "🏈 CFB PIPELINE"
    )
    print(
        "=" * 65
        + "\n"
    )

    cfb_odds = {}
    cfb_picks = None
    cfb_games = []

    # --------------------------------------------------------
    # STEP 5 — CFB ODDS
    # --------------------------------------------------------

    print(
        "🏈 STEP 5 — Fetching CFB odds..."
    )

    try:
        from odds_fetcher import (
            fetch_cfb_odds,
        )

        raw_cfb_odds = fetch_cfb_odds()

        if not raw_cfb_odds:

            raw_cfb_odds = load_json_file(
                f"logs/"
                f"{scrape_date}_cfb_odds.json",
                {},
            )

        cfb_odds = raw_cfb_odds

        from cfb_analyzer import (
            filter_cfb_slate,
        )

        cfb_games = filter_cfb_slate(
            cfb_odds.get(
                "games",
                [],
            ),
            scrape_date,
        )

        print(
            f"   📥 CFB games from API: "
            f"{len(cfb_odds.get('games', []))}"
        )

        print(
            f"   📅 CFB games on "
            f"{scrape_date}: "
            f"{len(cfb_games)}"
        )

        print(
            "✅ Step 5 complete\n"
        )

    except Exception as e:
        print(
            f"⚠️ CFB odds failed "
            f"(skipping): {e}\n"
        )

        cfb_games = []

    # --------------------------------------------------------
    # STEP 5.1 — CFB NEWS
    # Only use NewsAPI when CFB games exist TODAY.
    # --------------------------------------------------------

    if cfb_games:

        print(
            "📰 STEP 5.1 — Fetching CFB news..."
        )

        try:
            from news_fetcher import (
                fetch_cfb_news,
            )

            fetch_cfb_news(
                cfb_games,
                scrape_date,
            )

            print(
                "✅ Step 5.1 complete\n"
            )

        except Exception as e:
            print(
                f"⚠️ CFB news failed "
                f"(continuing): {e}\n"
            )

    else:
        print(
            f"ℹ️ No CFB games scheduled for "
            f"{scrape_date}."
        )

        print(
            "   Skipping CFB NewsAPI calls.\n"
        )

    # --------------------------------------------------------
    # STEP 5.2 — CFB ANALYZER
    #
    # analyze_cfb() has its own same-day filter and will
    # return without calling Claude when there are zero games.
    # --------------------------------------------------------

    print(
        "🧠 STEP 5.2 — Running CFB analyzer..."
    )

    try:
        from cfb_analyzer import (
            analyze_cfb,
        )

        cfb_picks = analyze_cfb(
            scrape_date
        )

        if cfb_picks:

            cfb_count = len(
                cfb_picks.get(
                    "top_picks",
                    cfb_picks.get(
                        "picks",
                        [],
                    ),
                )
            )

        else:
            cfb_count = 0

        print(
            f"✅ Step 5.2 complete — "
            f"{cfb_count} CFB pick(s)\n"
        )

    except Exception as e:
        print(
            f"⚠️ CFB analyzer failed "
            f"(skipping): {e}\n"
        )

        import traceback
        traceback.print_exc()

    # ========================================================
    # NBA
    # ========================================================

    print(
        "\n"
        + "=" * 65
    )
    print(
        "🏀 NBA PIPELINE"
    )
    print(
        "=" * 65
        + "\n"
    )

    nba_odds = {}
    nba_picks = None

    # --------------------------------------------------------
    # STEP 6 — NBA ODDS FIRST
    # --------------------------------------------------------

    print(
        "🏀 STEP 6 — Fetching NBA odds..."
    )

    try:
        from odds_fetcher import (
            fetch_nba_odds,
        )

        raw_nba_odds = fetch_nba_odds()

        if not raw_nba_odds:

            raw_nba_odds = load_json_file(
                f"logs/"
                f"{scrape_date}_nba_odds.json",
                {},
            )

        nba_odds = filter_daily_odds_data(
            raw_nba_odds,
            scrape_date,
        )

        raw_count = len(
            raw_nba_odds.get(
                "games",
                [],
            )
        )

        today_count = len(
            nba_odds.get(
                "games",
                [],
            )
        )

        print(
            f"   📥 NBA games from API: "
            f"{raw_count}"
        )

        print(
            f"   📅 NBA games on "
            f"{scrape_date}: "
            f"{today_count}"
        )

        print(
            "✅ Step 6 complete\n"
        )

    except Exception as e:
        print(
            f"⚠️ NBA odds failed "
            f"(skipping): {e}\n"
        )

        nba_odds = {}

    nba_game_count = len(
        nba_odds.get(
            "games",
            [],
        )
    )

    if nba_game_count > 0:

        # ----------------------------------------------------
        # STEP 6.1 — NBA PROPFINDER
        # ----------------------------------------------------

        print(
            "🏀 STEP 6.1 — Scraping NBA data..."
        )

        try:
            from scraper import run_nba_scraper

            try:
                await run_nba_scraper(
                    scrape_date
                )
            except TypeError:
                await run_nba_scraper()

            print(
                "✅ Step 6.1 complete\n"
            )

        except Exception as e:
            print(
                f"⚠️ NBA scraper failed "
                f"(continuing): {e}\n"
            )

        # ----------------------------------------------------
        # STEP 6.2 — NBA NEWS
        # ----------------------------------------------------

        print(
            "📰 STEP 6.2 — Fetching NBA news..."
        )

        try:
            from news_fetcher import (
                fetch_nba_news,
            )

            fetch_nba_news(
                nba_odds.get(
                    "games",
                    [],
                ),
                scrape_date,
            )

            print(
                "✅ Step 6.2 complete\n"
            )

        except Exception as e:
            print(
                f"⚠️ NBA news failed "
                f"(continuing): {e}\n"
            )

        # ----------------------------------------------------
        # STEP 6.3 — NBA ANALYSIS
        # ----------------------------------------------------

        print(
            "🧠 STEP 6.3 — Generating NBA picks..."
        )

        try:
            from nba_analyzer import (
                run_nba_analyzer,
            )

            nba_picks = run_nba_analyzer(
                scrape_date,
                nba_odds,
            )

            nba_count = len(
                nba_picks.get(
                    "top_picks",
                    [],
                )
            ) if nba_picks else 0

            print(
                f"✅ Step 6.3 complete — "
                f"{nba_count} NBA pick(s)\n"
            )

        except Exception as e:
            print(
                f"⚠️ NBA analyzer failed "
                f"(skipping): {e}\n"
            )

            import traceback
            traceback.print_exc()

    else:

        print(
            f"ℹ️ No NBA games scheduled for "
            f"{scrape_date}."
        )

        print(
            "   Skipping NBA PropFinder, news, "
            "and Claude analysis.\n"
        )

        nba_picks = {
            "league": "NBA",
            "top_picks": [],
            "picks": [],
            "best_bet": (
                "No NBA games scheduled today."
            ),
            "slate_summary": (
                "No NBA games scheduled today."
            ),
        }

    # ========================================================
    # EMAIL
    # ========================================================

    print(
        "\n"
        + "=" * 65
    )
    print(
        "📧 EMAIL"
    )
    print(
        "=" * 65
        + "\n"
    )

    print(
        "📧 STEP 7 — Sending combined picks email..."
    )

    try:
        from emailer import (
            send_picks_email,
        )

        picks_file = (
            f"logs/"
            f"{scrape_date}_picks.json"
        )

        if os.path.exists(
            picks_file
        ):

            picks_data = load_json_file(
                picks_file,
                {},
            )

            # ------------------------------------------------
            # Temporary compatibility layer.
            #
            # Your OLD emailer only accepts:
            # nba_picks
            #
            # The NEW emailer we build next will accept:
            # nba_picks
            # wnba_picks
            # cfb_picks
            #
            # This lets main.py work before and after
            # emailer.py is replaced.
            # ------------------------------------------------

            email_parameters = (
                inspect.signature(
                    send_picks_email
                ).parameters
            )

            if (
                "wnba_picks"
                in email_parameters
                and
                "cfb_picks"
                in email_parameters
            ):

                send_picks_email(
                    picks_data,
                    scrape_date,
                    graded_summary,
                    cumulative,
                    nba_picks=nba_picks,
                    wnba_picks=wnba_picks,
                    cfb_picks=cfb_picks,
                )

            else:

                print(
                    "⚠️ Current emailer.py does not "
                    "yet support WNBA + CFB."
                )

                print(
                    "   Sending using the existing "
                    "MLB/NBA email format for now."
                )

                send_picks_email(
                    picks_data,
                    scrape_date,
                    graded_summary,
                    cumulative,
                    nba_picks,
                )

            print(
                "✅ Step 7 complete\n"
            )

        else:
            print(
                f"❌ No MLB picks file found at "
                f"{picks_file}"
            )

            print(
                "⚠️ Email skipped.\n"
            )

    except Exception as e:
        print(
            f"❌ Emailer failed: {e}"
        )

        import traceback
        traceback.print_exc()

    # ========================================================
    # DONE
    # ========================================================

    end_time = get_eastern_now()

    duration = int(
        (
            end_time
            - start_time
        ).total_seconds()
    )

    minutes = duration // 60
    seconds = duration % 60

    mlb_count = (
        len(
            picks.get(
                "top_picks",
                [],
            )
        )
        if picks
        else 0
    )

    nrfi_count = (
        len(
            nrfi_picks
        )
        if nrfi_picks
        else 0
    )

    wnba_count = (
        len(
            wnba_picks.get(
                "top_picks",
                [],
            )
        )
        if wnba_picks
        else 0
    )

    cfb_count = (
        len(
            cfb_picks.get(
                "top_picks",
                cfb_picks.get(
                    "picks",
                    [],
                ),
            )
        )
        if cfb_picks
        else 0
    )

    nba_count = (
        len(
            nba_picks.get(
                "top_picks",
                [],
            )
        )
        if nba_picks
        else 0
    )

    print(
        f"\n{'=' * 65}"
    )
    print(
        f"✅ ALL DONE — {scrape_date}"
    )
    print(
        f"⏱️ Total time: "
        f"{minutes}m {seconds}s"
    )

    print(
        "\n📋 TODAY'S OUTPUT"
    )

    print(
        f"   🏀 WNBA: {wnba_count}"
    )
    print(
        f"   🏈 CFB:  {cfb_count}"
    )
    print(
        f"   ⚾ MLB:  {mlb_count}"
    )
    print(
        f"   🎰 NRFI: {nrfi_count}"
    )
    print(
        f"   🏀 NBA:  {nba_count}"
    )

    print(
        f"\n📧 Check your inbox for today's picks!"
    )

    print(
        f"{'=' * 65}\n"
    )


if __name__ == "__main__":
    asyncio.run(
        run_all()
    )