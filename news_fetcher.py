import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_API_URL = "https://newsapi.org/v2/everything"

NEWS_DOMAINS = (
    "espn.com,bleacherreport.com,cbssports.com,"
    "nbcsports.com,profootballtalk.nbcsports.com,"
    "theathletic.com,si.com,foxsports.com,"
    "nfl.com,mlb.com,nba.com,wnba.com,"
    "sportingnews.com,rotowire.com,rotoworld.com"
)


def fetch_articles_for_query(query, max_articles=3):
    """Fetch recent news articles for a given search query."""
    if not NEWS_API_KEY:
        print("   ⚠️ Missing NEWS_API_KEY")
        return []

    # Look back 2 days to catch recent recaps/injury updates.
    from_date = (
        datetime.now() - timedelta(days=2)
    ).strftime("%Y-%m-%d")

    params = {
        "q": query,
        "from": from_date,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": max_articles,
        "apiKey": NEWS_API_KEY,
        "domains": NEWS_DOMAINS,
    }

    try:
        response = requests.get(
            NEWS_API_URL,
            params=params,
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            articles = data.get("articles", [])

            return [
                {
                    "title": a.get("title", ""),
                    "description": a.get(
                        "description",
                        "",
                    ),
                    "source": a.get(
                        "source",
                        {},
                    ).get("name", ""),
                    "publishedAt": a.get(
                        "publishedAt",
                        "",
                    )[:10],
                    "url": a.get("url", ""),
                }
                for a in articles
                if (
                    a.get("title")
                    and "[Removed]"
                    not in a.get("title", "")
                )
            ]

        print(
            f"   ⚠️ NewsAPI error "
            f"{response.status_code}: "
            f"{response.text[:150]}"
        )

        return []

    except Exception as e:
        print(
            f"   ⚠️ News fetch error: {e}"
        )
        return []


def short_team_name(team):
    """
    Return a short team/mascot name.

    Examples:
      New York Yankees -> Yankees
      Indiana Fever -> Fever
      Ohio State Buckeyes -> Buckeyes
    """
    parts = team.split()

    return parts[-1] if parts else team


def fetch_sport_news(
    games,
    scrape_date,
    sport,
    max_requests=20,
):
    """
    Generic team-news fetcher for MLB/NBA/WNBA/CFB.

    Expected games format:
      {
          "home_team": "...",
          "away_team": "..."
      }

    CFB behavior:
      1. Search full team name first
      2. If nothing is found, search mascot/short name
    """
    sport_upper = sport.upper()

    print(
        f"\n📰 Fetching {sport_upper} news "
        f"for {len(games)} games..."
    )

    all_news = {}
    request_count = 0

    for game in games:
        home = game.get(
            "home_team",
            "",
        )

        away = game.get(
            "away_team",
            "",
        )

        if not home or not away:
            continue

        game_key = f"{away} @ {home}"

        for team in [home, away]:
            if request_count >= max_requests:
                print(
                    "   ⚠️ Request limit reached — "
                    "stopping news fetch"
                )
                break
            
            # ====================================================
            # CFB / NFL — full team name first
            # ====================================================
            if sport.lower() in ("cfb", "nfl"):
                league_phrase = (
                    "college football"
                    if sport.lower() == "cfb"
                    else "NFL"
                )

                query = f'"{team}" {league_phrase}'

                articles = fetch_articles_for_query(
                    query,
                    max_articles=2,
                )

                request_count += 1

                if (
                    not articles
                    and request_count < max_requests
                ):
                    short_name = short_team_name(team)

                    fallback_query = (
                        f'"{short_name}" '
                        f'{league_phrase}'
                    )

                    articles = fetch_articles_for_query(
                        fallback_query,
                        max_articles=2,
                    )

                    request_count += 1

            # ====================================================
            # MLB / NBA / WNBA
            # ====================================================
            else:
                short_name = short_team_name(team)

                query = (
                    f'"{short_name}" '
                    f'{sport_upper}'
                )

                articles = fetch_articles_for_query(
                    query,
                    max_articles=2,
                )

                request_count += 1

            # ====================================================
            # STORE RESULTS
            # ====================================================
            if articles:
                all_news.setdefault(
                    game_key,
                    [],
                )

                all_news[
                    game_key
                ].extend(
                    articles
                )

                print(
                    f"   ✅ {team}: "
                    f"{len(articles)} articles"
                )

            else:
                print(
                    f"   ⚠️ {team}: "
                    "no articles found"
                )

        if request_count >= max_requests:
            break

    print(
        f"   📊 Total news requests: "
        f"{request_count}"
    )

    print(
        f"   📊 Games with news: "
        f"{len(all_news)}"
    )

    filepath = (
        f"logs/{scrape_date}_"
        f"{sport.lower()}_news.json"
    )

    os.makedirs(
        "logs",
        exist_ok=True,
    )

    with open(
        filepath,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            all_news,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"   💾 Saved to {filepath}"
    )

    return all_news


def fetch_mlb_news(
    games,
    scrape_date,
):
    """Fetch recent MLB news for today's games."""
    return fetch_sport_news(
        games,
        scrape_date,
        sport="mlb",
        max_requests=20,
    )


def fetch_nba_news(
    games,
    scrape_date,
):
    """Fetch recent NBA news for today's games."""
    return fetch_sport_news(
        games,
        scrape_date,
        sport="nba",
        max_requests=20,
    )


def fetch_wnba_news(
    games,
    scrape_date,
):
    """Fetch recent WNBA news for today's games."""
    return fetch_sport_news(
        games,
        scrape_date,
        sport="wnba",
        max_requests=20,
    )


def fetch_cfb_news(
    games,
    scrape_date,
):
    """Fetch recent college football news."""
    return fetch_sport_news(
        games,
        scrape_date,
        sport="cfb",
        max_requests=30,
    )

def fetch_nfl_news(
    games,
    scrape_date,
):
    """Fetch recent NFL news for today's games."""
    return fetch_sport_news(
        games,
        scrape_date,
        sport="nfl",
        max_requests=40,
    )    


def format_news_for_prompt(
    news_data,
    sport="MLB",
):
    """
    Format saved news into concise prompt text.
    """
    if not news_data:
        return "No recent news available."

    text = ""

    for game_key, articles in (
        news_data.items()
    ):
        if not articles:
            continue

        text += (
            f"\n{game_key}:\n"
        )

        seen_titles = set()

        for article in articles[:4]:
            title = article.get(
                "title",
                "",
            ).strip()

            description = article.get(
                "description",
                "",
            ).strip()

            source = article.get(
                "source",
                "",
            )

            published_date = article.get(
                "publishedAt",
                "",
            )

            if (
                not title
                or title in seen_titles
            ):
                continue

            seen_titles.add(
                title
            )

            text += (
                f"  [{source} • "
                f"{published_date}] "
                f"{title}"
            )

            if (
                description
                and len(description) > 20
            ):
                text += (
                    f"\n  → "
                    f"{description[:180]}"
                )

            text += "\n"

    # Prevent news from becoming too large
    # inside the Claude prompt.
    return text[:6000]


def load_news(
    scrape_date,
    sport="mlb",
):
    """
    Load a saved sport-specific news file.
    """
    filepath = (
        f"logs/{scrape_date}_"
        f"{sport.lower()}_news.json"
    )

    if os.path.exists(
        filepath
    ):
        with open(
            filepath,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    return {}


# ============================================================
# MANUAL TEST
# ============================================================

if __name__ == "__main__":
    scrape_date = (
        datetime.now()
        .strftime("%Y-%m-%d")
    )

    test_cfb_games = [
        {
            "home_team": "TCU Horned Frogs",
            "away_team": "North Carolina Tar Heels",
        },
        {
            "home_team": "Texas Longhorns",
            "away_team": "Ohio State Buckeyes",
        },
    ]

    print(
        "Testing CFB news fetch..."
    )

    cfb_news = fetch_cfb_news(
        test_cfb_games,
        scrape_date,
    )

    print(
        "\nFormatted CFB news preview:"
    )

    print(
        format_news_for_prompt(
            cfb_news,
            "CFB",
        )[:2000]
    )