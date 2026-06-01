from __future__ import annotations

import configparser
import json
import os
import shutil
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from colorama import Fore, Style, init as colorama_init

APP_DIR_NAME = "TerminalQuoteGenerator"
CONFIG_FILENAME = "config.ini"
CACHE_FILENAME = "cache.json"
DEFAULT_INTERVAL_MINUTES = 60
DEFAULT_THEME_COLOR = "MAGENTA"
ZEN_QUOTES_URL = "https://zenquotes.io/api/random"

THEME_MAP = {
    "BLACK": Fore.BLACK,
    "BLUE": Fore.BLUE,
    "CYAN": Fore.CYAN,
    "GREEN": Fore.GREEN,
    "LIGHTBLACK_EX": Fore.LIGHTBLACK_EX,
    "LIGHTBLUE_EX": Fore.LIGHTBLUE_EX,
    "LIGHTCYAN_EX": Fore.LIGHTCYAN_EX,
    "LIGHTGREEN_EX": Fore.LIGHTGREEN_EX,
    "LIGHTMAGENTA_EX": Fore.LIGHTMAGENTA_EX,
    "LIGHTRED_EX": Fore.LIGHTRED_EX,
    "LIGHTWHITE_EX": Fore.LIGHTWHITE_EX,
    "LIGHTYELLOW_EX": Fore.LIGHTYELLOW_EX,
    "MAGENTA": Fore.MAGENTA,
    "RED": Fore.RED,
    "WHITE": Fore.WHITE,
    "YELLOW": Fore.YELLOW,
}


@dataclass(frozen=True)
class Quote:
    text: str
    author: str
    fetched_at: datetime


def main() -> int:
    colorama_init(autoreset=True)

    app_dir = get_app_dir()
    app_dir.mkdir(parents=True, exist_ok=True)

    config_path = app_dir / CONFIG_FILENAME
    cache_path = app_dir / CACHE_FILENAME

    settings = load_or_create_config(config_path)
    interval_minutes = parse_interval_minutes(settings.get("interval_minutes", str(DEFAULT_INTERVAL_MINUTES)))
    theme_color = normalize_theme_color(settings.get("theme_color", DEFAULT_THEME_COLOR))
    accent = THEME_MAP.get(theme_color, Fore.MAGENTA)

    cached_quote = load_cache(cache_path)
    quote = choose_quote(cache_path, cached_quote, interval_minutes)

    if quote is None:
        print_error(accent, "No quote available yet. Connect to the internet once to seed the cache.")
        return 1

    render_quote(quote, accent)
    return 0


def get_app_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / APP_DIR_NAME


def load_or_create_config(config_path: Path) -> configparser.SectionProxy:
    parser = configparser.ConfigParser()
    settings_section = "Settings"

    if config_path.exists():
        parser.read(config_path, encoding="utf-8")
        if settings_section not in parser:
            parser[settings_section] = {}
    else:
        parser[settings_section] = {
            "interval_minutes": str(DEFAULT_INTERVAL_MINUTES),
            "theme_color": DEFAULT_THEME_COLOR,
        }
        with config_path.open("w", encoding="utf-8") as handle:
            parser.write(handle)
        return parser[settings_section]

    settings = parser[settings_section]
    changed = False
    if "interval_minutes" not in settings:
        settings["interval_minutes"] = str(DEFAULT_INTERVAL_MINUTES)
        changed = True
    if "theme_color" not in settings:
        settings["theme_color"] = DEFAULT_THEME_COLOR
        changed = True

    if changed:
        with config_path.open("w", encoding="utf-8") as handle:
            parser.write(handle)

    return settings


def parse_interval_minutes(value: str) -> int:
    try:
        parsed = int(value)
        return max(1, parsed)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_MINUTES


def normalize_theme_color(value: str) -> str:
    if not value:
        return DEFAULT_THEME_COLOR
    cleaned = value.strip().upper()
    return cleaned if cleaned in THEME_MAP else DEFAULT_THEME_COLOR


def load_cache(cache_path: Path) -> Quote | None:
    if not cache_path.exists():
        return None

    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        text = str(raw["quote"]).strip()
        author = str(raw["author"]).strip()
        fetched_at = datetime.fromisoformat(str(raw["timestamp"]))
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        return Quote(text=text, author=author, fetched_at=fetched_at)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, OSError):
        return None


def save_cache(cache_path: Path, quote: Quote) -> None:
    payload = {
        "quote": quote.text,
        "author": quote.author,
        "timestamp": quote.fetched_at.astimezone(timezone.utc).isoformat(),
    }
    cache_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def choose_quote(cache_path: Path, cached_quote: Quote | None, interval_minutes: int) -> Quote | None:
    now = datetime.now(timezone.utc)

    if cached_quote is not None:
        elapsed_minutes = (now - cached_quote.fetched_at).total_seconds() / 60.0
        if elapsed_minutes < interval_minutes:
            return cached_quote

    fresh_quote = fetch_quote()
    if fresh_quote is not None:
        save_cache(cache_path, fresh_quote)
        return fresh_quote

    return cached_quote


def fetch_quote() -> Quote | None:
    request = urllib.request.Request(
        ZEN_QUOTES_URL,
        headers={"User-Agent": "TerminalQuoteGenerator/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    if not isinstance(payload, list) or not payload:
        return None

    first = payload[0]
    if not isinstance(first, dict):
        return None

    text = str(first.get("q", "")).strip()
    author = str(first.get("a", "")).strip() or "Unknown"
    if not text:
        return None

    return Quote(text=text, author=author, fetched_at=datetime.now(timezone.utc))


def render_quote(quote: Quote, accent: str) -> None:
    width = max(40, shutil.get_terminal_size(fallback=(80, 20)).columns)
    inner_width = max(20, width - 6)
    wrapped_quote_lines = textwrap.wrap(
        quote.text,
        width=inner_width,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [quote.text]

    author_line = f"- {quote.author}"
    author_right = author_line.rjust(inner_width)
    content_lines = wrapped_quote_lines + [author_right]

    border = f"{accent}+{'-' * (inner_width + 2)}+{Style.RESET_ALL}"
    print(border)
    for line in content_lines:
        padded = line.ljust(inner_width)
        print(f"{accent}| {Style.RESET_ALL}{padded}{accent} |{Style.RESET_ALL}")
    print(border)


def print_error(accent: str, message: str) -> None:
    print(f"{accent}quote-gen:{Style.RESET_ALL} {message}")


if __name__ == "__main__":
    sys.exit(main())
