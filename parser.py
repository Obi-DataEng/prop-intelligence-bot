"""Parse raw MLB PropFinder scraper output into structured JSON.

Usage:
    python parser.py
    python parser.py 2026-09-03
    python parser.py 2026-09-03 --logs-dir logs

The parser keeps raw rows when a page is not structured enough to parse
reliably. This prevents useful scraper data from being silently discarded.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional


TEAM_RE = re.compile(r"^[A-Z]{2,4}$")
PITCHER_RE = re.compile(r"^(LHP|RHP)\s+(.+)$", re.IGNORECASE)
NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
ODDS_RE = re.compile(r"^[+-]\d+$")
TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}\s*(?:AM|PM))\b", re.IGNORECASE)
TEMP_RE = re.compile(r"(-?\d{1,3})\s*°?\s*F\b", re.IGNORECASE)
WIND_RE = re.compile(r"(?:wind[^\d]{0,15})?(\d{1,3})\s*MPH\b", re.IGNORECASE)
PRECIP_RE = re.compile(
    r"(?:precip(?:itation)?|rain|chance)[^\d]{0,20}(\d{1,3})\s*%",
    re.IGNORECASE,
)


def clean_lines(text: str) -> list[str]:
    """Return non-empty, whitespace-normalized lines."""
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def first_number(value: str) -> Optional[float]:
    match = NUMBER_RE.search(value or "")
    return float(match.group()) if match else None


def parse_pitcher(value: str) -> tuple[str, Optional[str]]:
    """Return pitcher name and L/R hand; TBD has no assumed hand."""
    value = re.sub(r"\s+", " ", value or "").strip()
    if not value or "TBD" in value.upper():
        return value or "Pitcher TBD", None

    match = PITCHER_RE.match(value)
    if not match:
        return value, None

    return match.group(2).strip(), match.group(1)[0].upper()


def is_pitcher_line(value: str) -> bool:
    upper = (value or "").upper()
    return bool(PITCHER_RE.match(value or "")) or "PITCHER TBD" in upper


def lineup_confirmed(values: Iterable[str]) -> bool:
    text = " ".join(values).casefold()
    if any(marker in text for marker in ("projected lineup", "unconfirmed lineup", "lineup tbd")):
        return False
    return "✓" in text or "confirmed lineup" in text or "lineup confirmed" in text


def find_label_value(lines: list[str], start: int, stop: int, label: str) -> Optional[str]:
    """Find a label and return the next meaningful line in the same game block."""
    label_cf = label.casefold()
    for index in range(start, min(stop, len(lines))):
        current = lines[index].casefold().rstrip(":")
        if current == label_cf:
            for value_index in range(index + 1, min(index + 4, stop, len(lines))):
                candidate = lines[value_index].strip()
                if candidate and candidate.casefold().rstrip(":") != label_cf:
                    return candidate
        if current.startswith(f"{label_cf} "):
            return lines[index][len(label) :].strip(" :")
    return None


def find_moneylines(lines: list[str], start: int, stop: int) -> list[str]:
    """Find up to two American prices after an ML label."""
    for index in range(start, min(stop, len(lines))):
        if lines[index].casefold().rstrip(":") in {"ml", "moneyline"}:
            prices: list[str] = []
            for candidate in lines[index + 1 : min(index + 8, stop, len(lines))]:
                if ODDS_RE.fullmatch(candidate):
                    prices.append(candidate)
                    if len(prices) == 2:
                        return prices
            return prices
    return []


def parse_ou(value: Optional[str]) -> tuple[Optional[str], Optional[float]]:
    if not value:
        return None, None
    side_match = re.search(r"\b(Over|Under|O|U)\b", value, re.IGNORECASE)
    side = None
    if side_match:
        side = "Over" if side_match.group(1).upper() in {"O", "OVER"} else "Under"
    return side, first_number(value)


CONSENSUS_CARD_RE = re.compile(
    r"(?ms)^([A-Z]{2,4})\s+\(([^)]*)\)\s*\n\s*"
    r"\((\d+-\d+)\).*?^vs\s*$\s*\n\s*"
    r"([A-Z]{2,4})\s+\(([^)]*)\)\s*\n\s*"
    r"\((\d+-\d+)\).*?^Winner:\s*([A-Z]{2,4})"
    r"(?:\s+([+-]?\d+))?\s*$"
)


def parse_winner_projection_cards(raw_text: str, source: str = "consensus") -> list[dict[str, Any]]:
    """Parse PropFinder's current MLB Model/Consensus winner-card layout."""
    games: list[dict[str, Any]] = []
    matches = list(CONSENSUS_CARD_RE.finditer(raw_text or ""))
    for index, match in enumerate(matches):
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
        block = clean_lines(raw_text[match.start():block_end])
        time_value = next((TIME_RE.search(line).group(1).upper() for line in block if TIME_RE.search(line)), None)
        home_team, home_price, home_record, away_team, away_price, away_record, winner, winner_price = match.groups()
        games.append({
            "home_team": home_team,
            "away_team": away_team,
            "home_record": home_record,
            "away_record": away_record,
            "home_model_price": first_number(home_price),
            "away_model_price": first_number(away_price),
            "model_winner": winner,
            "model_winner_price": first_number(winner_price or ""),
            "projection_source": source,
            "game_time": time_value,
            "home_proj_runs": None,
            "away_proj_runs": None,
            "display_order": "home_vs_away",
            "raw_block": block,
        })
    return games


def parse_projection_views(section: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge Model 1, Model 2, and Consensus winner selections by matchup."""
    views = section.get("views", {}) if isinstance(section, dict) else {}
    if not views:
        return parse_projections(full_text_from(section))

    merged: dict[frozenset[str], dict[str, Any]] = {}
    for source in ("model_1", "model_2", "consensus"):
        view = views.get(source, {})
        for game in parse_winner_projection_cards(str(view.get("fullText", "")), source):
            key = frozenset((game["home_team"], game["away_team"]))
            record = merged.setdefault(key, dict(game))
            record[f"{source}_winner"] = game["model_winner"]
            record[f"{source}_winner_price"] = game["model_winner_price"]
            if source == "consensus":
                record.update(game)

    for game in merged.values():
        winners = [game.get("model_1_winner"), game.get("model_2_winner")]
        game["model_winner"] = (
            game.get("consensus_winner")
            or (winners[0] if winners[0] and winners[0] == winners[1] else None)
        )
        game["models_agree"] = bool(winners[0] and winners[0] == winners[1])
    return list(merged.values())


def parse_projections(raw_text: str) -> list[dict[str, Any]]:
    """Parse projection cards from page fullText.

    PropFinder historically displays the home team before ``vs``. The original
    field names are retained for compatibility. Each result also includes
    ``display_order`` so this assumption remains visible downstream.
    """
    current_cards = parse_winner_projection_cards(raw_text)
    if current_cards:
        return current_cards

    lines = clean_lines(raw_text)
    games: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    i = 0

    while i < len(lines) - 1:
        if not TEAM_RE.fullmatch(lines[i]) or not is_pitcher_line(lines[i + 1]):
            i += 1
            continue

        first_team_index = i
        vs_index = next(
            (j for j in range(i + 2, min(i + 18, len(lines))) if lines[j].casefold() in {"vs", "@"}),
            None,
        )
        if vs_index is None or vs_index + 2 >= len(lines):
            i += 1
            continue

        second_team_index = vs_index + 1
        if not TEAM_RE.fullmatch(lines[second_team_index]) or not is_pitcher_line(
            lines[second_team_index + 1]
        ):
            i += 1
            continue

        next_game = next(
            (
                j
                for j in range(second_team_index + 2, len(lines) - 1)
                if TEAM_RE.fullmatch(lines[j]) and is_pitcher_line(lines[j + 1])
            ),
            len(lines),
        )
        block_stop = min(next_game, first_team_index + 60)
        block = lines[first_team_index:block_stop]

        home_pitcher, home_hand = parse_pitcher(lines[first_team_index + 1])
        away_pitcher, away_hand = parse_pitcher(lines[second_team_index + 1])

        projected_runs: list[float] = []
        for index in range(first_team_index, block_stop):
            current = lines[index].casefold().rstrip(":")
            if current in {"proj runs", "projected runs"} and index + 1 < block_stop:
                value = first_number(lines[index + 1])
                if value is not None:
                    projected_runs.append(value)
            else:
                inline = re.search(
                    r"proj(?:ected)?\s+runs?\s*:?\s*(-?\d+(?:\.\d+)?)",
                    lines[index],
                    re.IGNORECASE,
                )
                if inline:
                    projected_runs.append(float(inline.group(1)))

        # Fall back to decimal values only when labeled projections were absent.
        if len(projected_runs) < 2:
            labeled_values = {
                first_number(value)
                for value in block
                if any(label in value.casefold() for label in ("o/u", "odds", "spread", "moneyline"))
            }
            candidates = [
                float(value)
                for value in block
                if re.fullmatch(r"\d{1,2}\.\d+", value)
                and float(value) not in labeled_values
                and 0.0 <= float(value) <= 20.0
            ]
            projected_runs = candidates[:2]

        ou_raw = find_label_value(lines, first_team_index, block_stop, "O/U")
        ou_side, ou_line = parse_ou(ou_raw)
        moneylines = find_moneylines(lines, first_team_index, block_stop)

        key = (lines[first_team_index], lines[second_team_index], home_pitcher, away_pitcher)
        if key not in seen:
            games.append(
                {
                    "home_team": lines[first_team_index],
                    "home_pitcher": home_pitcher,
                    "home_pitcher_hand": home_hand,
                    "home_lineup": lineup_confirmed(lines[first_team_index + 2 : vs_index]),
                    "away_team": lines[second_team_index],
                    "away_pitcher": away_pitcher,
                    "away_pitcher_hand": away_hand,
                    "away_lineup": lineup_confirmed(lines[second_team_index + 2 : block_stop]),
                    "home_proj_runs": projected_runs[0] if projected_runs else None,
                    "away_proj_runs": projected_runs[1] if len(projected_runs) > 1 else None,
                    "ou_side": ou_side,
                    "ou_line": ou_line,
                    "home_ml": moneylines[0] if moneylines else None,
                    "away_ml": moneylines[1] if len(moneylines) > 1 else None,
                    "display_order": "home_vs_away",
                    "raw_block": block,
                }
            )
            seen.add(key)

        i = max(second_team_index + 2, next_game)

    return games


def parse_projections_simple(raw_text: str) -> list[dict[str, Any]]:
    """Backward-compatible alias used by the existing scraper pipeline."""
    return parse_projections(raw_text)


def split_row(row: str) -> list[str]:
    if "\t" in row:
        values = row.split("\t")
    else:
        values = re.split(r"\s{2,}", row.replace("\u00a0", " "))
    return [re.sub(r"\s+", " ", value).strip() for value in values if value.strip()]


def parse_weather(rows: Iterable[str]) -> list[dict[str, Any]]:
    """Parse weather rows without treating an arbitrary percentage as rain."""
    weather_data: list[dict[str, Any]] = []
    for row in rows:
        if not row:
            continue
        temp_match = TEMP_RE.search(row)
        if not temp_match:
            continue

        precip_match = PRECIP_RE.search(row)
        wind_match = WIND_RE.search(row)
        time_match = TIME_RE.search(row)
        parts = split_row(row)

        weather_data.append(
            {
                "temp": int(temp_match.group(1)),
                "precip": int(precip_match.group(1)) if precip_match else None,
                "wind_speed": int(wind_match.group(1)) if wind_match else None,
                "game_time": time_match.group(1).upper() if time_match else None,
                "parts": parts,
                "raw": row,
            }
        )
    return weather_data


def parse_pitcher_summary(rows: Iterable[str]) -> list[dict[str, Any]]:
    pitchers: list[dict[str, Any]] = []
    for row in rows:
        if not row:
            continue
        parts = split_row(row)
        upper_parts = {part.upper() for part in parts}
        if upper_parts.intersection({"PITCHER", "NAME", "TEAM", "SPLIT"}):
            continue
        if len(parts) >= 4:
            pitchers.append({"raw": row, "parts": parts})
    return pitchers


def parse_park_factors(rows: Iterable[str]) -> list[dict[str, Any]]:
    parks: list[dict[str, Any]] = []
    for row in rows:
        if not row or "PARK" in row.upper() and "FACTOR" in row.upper():
            continue
        parts = split_row(row)
        factors = [float(value) for value in NUMBER_RE.findall(row)]
        if len(factors) >= 2:
            parks.append({"raw": row, "parts": parts, "factors": factors})
    return parks


def rows_from(section: Any) -> list[str]:
    if not isinstance(section, dict):
        return []
    rows = section.get("rows", [])
    return [str(row) for row in rows] if isinstance(rows, list) else []


def full_text_from(section: Any) -> str:
    if not isinstance(section, dict):
        return ""
    return str(section.get("fullText") or section.get("full_text") or "")


def run_parser(raw_data: dict[str, Any], scrape_date: str) -> dict[str, Any]:
    print(f"\n{'=' * 50}")
    print(f"🔍 Parsing scraped data for {scrape_date}")
    print(f"{'=' * 50}\n")

    parsed: dict[str, Any] = {"scrape_date": scrape_date}

    if raw_data.get("projections"):
        parsed["games"] = parse_projection_views(raw_data["projections"])
        print(f"✅ Games parsed: {len(parsed['games'])}")
        for game in parsed["games"][:3]:
            print(
                f"   {game['home_team']} vs {game['away_team']} | "
                f"Proj: {game['home_proj_runs']} - {game['away_proj_runs']} | "
                f"O/U: {game.get('ou_line', 'market consensus')}"
            )
    else:
        parsed["games"] = []

    parsed["weather"] = parse_weather(rows_from(raw_data.get("weather")))
    parsed["pitchers"] = parse_pitcher_summary(rows_from(raw_data.get("pitcher_summary")))
    parsed["park_factors"] = parse_park_factors(rows_from(raw_data.get("park_factors")))
    parsed["hr_matchups_text"] = "\n".join(rows_from(raw_data.get("hr_matchups")))
    parsed["exit_velo_text"] = "\n".join(rows_from(raw_data.get("exit_velo")))

    print(f"✅ Weather entries parsed: {len(parsed['weather'])}")
    print(f"✅ Pitcher rows parsed: {len(parsed['pitchers'])}")
    print(f"✅ Park factor rows parsed: {len(parsed['park_factors'])}")
    print(f"✅ HR matchups text ready: {len(parsed['hr_matchups_text'])} chars")
    print(f"✅ Exit velo text ready: {len(parsed['exit_velo_text'])} chars")
    print("\n✅ Parsing complete!")
    return parsed


def load_raw_data(logs_dir: Path, scrape_date: str) -> dict[str, Any]:
    raw_data: dict[str, Any] = {}
    tabs = (
        "hr_matchups",
        "exit_velo",
        "pitcher_summary",
        "park_factors",
        "weather",
        "projections",
    )
    for tab in tabs:
        path = logs_dir / f"{scrape_date}_{tab}.json"
        if not path.exists():
            print(f"⚠️  Missing {path}")
            continue
        try:
            with path.open("r", encoding="utf-8") as file:
                raw_data[tab] = json.load(file)
            print(f"📂 Loaded {tab}")
        except (OSError, json.JSONDecodeError) as error:
            print(f"❌ Could not load {path}: {type(error).__name__}: {error}")
    return raw_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse saved MLB scraper JSON files.")
    parser.add_argument(
        "scrape_date",
        nargs="?",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Snapshot date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument("--logs-dir", default="logs", help="Directory containing scraper JSON")
    parser.add_argument(
        "--output",
        help="Output JSON path (default: logs/YYYY-MM-DD_parsed.json)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        datetime.strptime(args.scrape_date, "%Y-%m-%d")
    except ValueError:
        print("❌ scrape_date must use YYYY-MM-DD format")
        return 2

    logs_dir = Path(args.logs_dir)
    raw_data = load_raw_data(logs_dir, args.scrape_date)
    if not raw_data:
        print("❌ No source files were loaded; nothing to parse.")
        return 1

    parsed = run_parser(raw_data, args.scrape_date)
    output_path = Path(args.output) if args.output else logs_dir / f"{args.scrape_date}_parsed.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(parsed, file, indent=2, ensure_ascii=False)
    print(f"💾 Saved parsed data to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
