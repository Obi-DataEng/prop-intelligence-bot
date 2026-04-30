import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_API_URL = "https://newsapi.org/v2/everything"


def fetch_articles_for_query(query, max_articles=3):
    """Fetch recent news articles for a given search query"""
    if not NEWS_API_KEY:
        return []

    # Look back 2 days to catch yesterday's recaps
    from_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

    params = {
        "q": query,
        "from": from_date,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": max_articles,
        "apiKey": NEWS_API_KEY,
        "domains": (
            "espn.com,bleacherreport.com,cbssports.com,"
            "nbcsports.com,theathletic.com,mlb.com,nba.com,"
            "sportingnews.com,rotowire.com,rotoworld.com"
        )
    }

    try:
        response = requests.get(NEWS_API_URL, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            articles = data.get("articles", [])
            return [
                {
                    "title": a.get("title", ""),
                    "description": a.get("description", ""),
                    "source": a.get("source", {}).get("name", ""),
                    "publishedAt": a.get("publishedAt", "")[:10]
                }
                for a in articles
                if a.get("title") and "[Removed]" not in a.get("title", "")
            ]
        else:
            print(f"   ⚠️ NewsAPI error {response.status_code}: {response.text[:100]}")
            return []
    except Exception as e:
        print(f"   ⚠️ News fetch error: {e}")
        return []


def fetch_mlb_news(games, scrape_date):
    """Fetch news for all MLB games on today's slate"""
    print(f"\n📰 Fetching MLB news for {len(games)} games...")

    all_news = {}
    request_count = 0

    for game in games:
        home = game.get("home_team", "")
        away = game.get("away_team", "")
        game_key = f"{away} @ {home}"

        # Search for each team
        for team in [home, away]:
            if request_count >= 20:  # Stay well within free tier
                print(f"   ⚠️ Request limit reached — stopping news fetch")
                break

            # Shorten team names for better search results
            short_name = team.split()[-1]  # e.g. "Yankees" from "New York Yankees"
            query = f"{short_name} MLB"

            articles = fetch_articles_for_query(query, max_articles=2)
            request_count += 1

            if articles:
                if game_key not in all_news:
                    all_news[game_key] = []
                all_news[game_key].extend(articles)
                print(f"   ✅ {team}: {len(articles)} articles")
            else:
                print(f"   ⚠️ {team}: no articles found")

        if request_count >= 20:
            break

    print(f"   📊 Total news requests: {request_count}")
    print(f"   📊 Games with news: {len(all_news)}")

    # Save to logs
    filepath = f"logs/{scrape_date}_mlb_news.json"
    with open(filepath, "w") as f:
        json.dump(all_news, f, indent=2)
    print(f"   💾 Saved to {filepath}")

    return all_news


def fetch_nba_news(games, scrape_date):
    """Fetch news for all NBA games on today's slate"""
    print(f"\n📰 Fetching NBA news for {len(games)} games...")

    all_news = {}
    request_count = 0

    for game in games:
        home = game.get("home_team", "")
        away = game.get("away_team", "")
        game_key = f"{away} @ {home}"

        for team in [home, away]:
            if request_count >= 20:
                print(f"   ⚠️ Request limit reached — stopping news fetch")
                break

            short_name = team.split()[-1]  # e.g. "Celtics"
            query = f"{short_name} NBA"

            articles = fetch_articles_for_query(query, max_articles=2)
            request_count += 1

            if articles:
                if game_key not in all_news:
                    all_news[game_key] = []
                all_news[game_key].extend(articles)
                print(f"   ✅ {team}: {len(articles)} articles")
            else:
                print(f"   ⚠️ {team}: no articles found")

        if request_count >= 20:
            break

    print(f"   📊 Total news requests: {request_count}")
    print(f"   📊 Games with news: {len(all_news)}")

    filepath = f"logs/{scrape_date}_nba_news.json"
    with open(filepath, "w") as f:
        json.dump(all_news, f, indent=2)
    print(f"   💾 Saved to {filepath}")

    return all_news


def format_news_for_prompt(news_data, sport="MLB"):
    """Format news articles into readable text for Claude prompt"""
    if not news_data:
        return "No recent news available."

    text = ""
    for game_key, articles in news_data.items():
        if not articles:
            continue

        text += f"\n{game_key}:\n"
        seen_titles = set()

        for article in articles[:4]:  # Max 4 articles per game
            title = article.get("title", "").strip()
            desc = article.get("description", "").strip()
            source = article.get("source", "")
            date = article.get("publishedAt", "")

            if title in seen_titles or not title:
                continue
            seen_titles.add(title)

            text += f"  [{source} • {date}] {title}"
            if desc and len(desc) > 20:
                # Truncate description to keep tokens low
                text += f"\n  → {desc[:150]}"
            text += "\n"

    return text[:6000]  # Cap at 6000 chars to control token usage


def load_news(scrape_date, sport="mlb"):
    """Load saved news file"""
    filepath = f"logs/{scrape_date}_{sport}_news.json"
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    # Test run
    scrape_date = datetime.now().strftime("%Y-%m-%d")

    # Mock games for testing
    test_mlb_games = [
        {"home_team": "New York Yankees", "away_team": "Boston Red Sox"},
        {"home_team": "Los Angeles Dodgers", "away_team": "San Francisco Giants"},
    ]

    test_nba_games = [
        {"home_team": "Boston Celtics", "away_team": "Philadelphia 76ers"},
        {"home_team": "Denver Nuggets", "away_team": "Minnesota Timberwolves"},
    ]

    print("Testing MLB news fetch...")
    mlb_news = fetch_mlb_news(test_mlb_games, scrape_date)
    print(f"\nFormatted MLB news preview:")
    print(format_news_for_prompt(mlb_news)[:500])

    print("\n" + "="*50)
    print("Testing NBA news fetch...")
    nba_news = fetch_nba_news(test_nba_games, scrape_date)
    print(f"\nFormatted NBA news preview:")
    print(format_news_for_prompt(nba_news, "NBA")[:500])