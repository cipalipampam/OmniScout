import asyncio
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from rich.console import Console
    from rich.table import Table
    from rich.prompt import Prompt
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from src.auth import get_all_sessions_status, is_session_valid, setup_threads_login, setup_x_login
from configs.config import EXPORTS_DIR, THREADS_PROFILE_DIR, X_PROFILE_DIR
from src.pipeline import run_pipeline_sync

console = Console() if HAS_RICH else None


def info(message: str):
    (console.print if HAS_RICH else print)(f"[INFO] {message}" if not HAS_RICH else f"[cyan][INFO][/cyan] {message}")


def success(message: str):
    (console.print if HAS_RICH else print)(f"[OK] {message}" if not HAS_RICH else f"[green][OK][/green] {message}")


def warning(message: str):
    (console.print if HAS_RICH else print)(f"[WARN] {message}" if not HAS_RICH else f"[yellow][WARN][/yellow] {message}")


def error(message: str):
    (console.print if HAS_RICH else print)(f"[ERROR] {message}" if not HAS_RICH else f"[red][ERROR][/red] {message}")


def display_banner():
    title = "SOCIAL MEDIA DATA SCRAPER"
    subtitle = "X (Twitter) & Threads | Keyword and URL collection"
    if HAS_RICH:
        console.print(f"\n[bold cyan]{title}[/bold cyan]\n[dim]{subtitle}[/dim]\n")
    else:
        print(f"\n{title}\n{subtitle}\n")


def show_auth_status():
    statuses = get_all_sessions_status()
    if HAS_RICH:
        table = Table(title="Browser session status")
        table.add_column("Platform")
        table.add_column("Valid")
        table.add_column("Message")
        for key, value in statuses.items():
            table.add_row(key.upper(), "yes" if value.get("is_valid") else "no", value.get("message", ""))
        console.print(table)
    else:
        for key, value in statuses.items():
            print(f"{key.upper()}: {'valid' if value.get('is_valid') else 'invalid'} - {value.get('message', '')}")


def login_platform(platform: str):
    profile = str(X_PROFILE_DIR if platform == "x" else THREADS_PROFILE_DIR)
    login = setup_x_login if platform == "x" else setup_threads_login
    try:
        success(f"Opening interactive {platform.upper()} login.")
        result = asyncio.run(login(profile))
        success("Login completed." if result else "Login did not complete.")
    except Exception as exc:
        error(f"Login failed: {exc}")


def prompt_value(label: str, default: str = "") -> str:
    if HAS_RICH:
        return Prompt.ask(label, default=default)
    return input(f"{label}{f' [{default}]' if default else ''}: ").strip() or default


def run_scrape():
    platform = prompt_value("Platform (x/threads/both)", "both").lower()
    search_mode = prompt_value("Search mode (latest/top)", "latest").lower()
    keywords = [item.strip() for item in prompt_value("Keywords (comma separated)").split(",") if item.strip()]
    direct_urls = [item.strip() for item in prompt_value("Direct URLs (comma separated)", "").split(",") if item.strip()]
    if not keywords and not direct_urls:
        warning("At least one keyword or direct URL is required.")
        return

    try:
        max_links = int(prompt_value("Maximum links per keyword", "30"))
        max_scroll_steps = int(prompt_value("Maximum discovery scroll steps", "200"))
    except ValueError:
        warning("Invalid numeric value.")
        return

    headless = prompt_value("Run headless? (y/n)", "n").lower() == "y"

    def status_callback(message: str):
        info(message)

    try:
        result = run_pipeline_sync(
            keywords=keywords,
            direct_urls=direct_urls,
            platform=platform,
            search_mode=search_mode,
            max_links=max_links,
            max_scroll_steps=max_scroll_steps,
            headless=headless,
            export_csv=True,
            status_callback=status_callback,
        )
    except Exception as exc:
        error(f"Scraping failed: {exc}")
        return

    if result.get("status") != "success":
        warning(result.get("message", "Scraping did not produce data."))
        for detail in result.get("errors", []):
            warning(str(detail))
        return

    stats = result.get("statistics", {})
    success(f"Collected {result.get('total_data', 0):,} rows.")
    info(f"Export: {result.get('exported_file')}")
    info(f"Unique users: {stats.get('unique_users', 0):,}")
    info(f"Unique sources: {stats.get('unique_sources', 0):,}")
    preview = result.get("dataframe", pd.DataFrame())
    if not preview.empty:
        print(preview.head(3).to_string(index=False))


def main():
    while True:
        display_banner()
        print("1. Check login sessions")
        print("2. Login X")
        print("3. Login Threads")
        print("4. Run scraping")
        print("5. List exports")
        print("0. Exit")
        choice = prompt_value("Choose", "0")

        if choice == "0":
            return
        if choice == "1":
            show_auth_status()
        elif choice == "2":
            login_platform("x")
        elif choice == "3":
            login_platform("threads")
        elif choice == "4":
            run_scrape()
        elif choice == "5":
            files = sorted(EXPORTS_DIR.glob("*.csv"))
            for file in files:
                print(file.name)
            if not files:
                info("No CSV exports found.")
        else:
            warning("Unknown menu choice.")

        input("\nPress Enter to continue...")


if __name__ == "__main__":
    main()
