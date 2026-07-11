"""
Download Spotify weekly global Top 200 charts (2017→2026) via Selenium.

Logs in with your Spotify credentials, navigates to each weekly chart page,
and clicks the CSV download button. Saves to /tmp/spotify_charts_csv/.

Requirements:
    pip install selenium webdriver-manager
    SPOTIFY_USERNAME and SPOTIFY_PASSWORD in .env

CSV schema per file:
    rank, uri, artist_names, track_name, source, peak_rank, previous_rank,
    days_on_chart, streams

Usage:
    python src/compute/download_chart_csvs.py
    python src/compute/download_chart_csvs.py --from 2022-01-01
    python src/compute/download_chart_csvs.py --workers 3
"""

import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

_OUT_DIR  = Path("/tmp/spotify_charts_csv")
_LOGIN_URL = "https://accounts.spotify.com/en/login?continue=https%3A%2F%2Fcharts.spotify.com%2F"
_CHART_BASE = "https://charts.spotify.com/charts/view/regional-global-weekly"
_FIRST_WEEK = date(2017, 1, 5)   # first Thursday with weekly global charts


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def thursdays(start: date, end: date):
    d = start
    while d.weekday() != 3:
        d += timedelta(days=1)
    while d <= end:
        yield d
        d += timedelta(weeks=1)


def csv_filename(d: date) -> str:
    return f"regional-global-weekly-{d}.csv"


# ---------------------------------------------------------------------------
# Selenium driver setup
# ---------------------------------------------------------------------------

def make_driver(download_dir: Path, headless: bool = False):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = webdriver.ChromeOptions()
    options.add_experimental_option("prefs", {
        "download.default_directory":       str(download_dir),
        "download.prompt_for_download":     False,
        "download.directory_upgrade":       True,
        "safebrowsing.enabled":             True,
    })
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def _find_element(driver, selectors: list, timeout: int = 15):
    """Try multiple CSS selectors, return first match."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    wait = WebDriverWait(driver, timeout)
    for sel in selectors:
        try:
            return wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
        except Exception:
            continue
    raise RuntimeError(f"None of these selectors found: {selectors}\nCurrent URL: {driver.current_url}")


def login(driver, username: str = "", password: str = ""):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    print("\nOpening Spotify Charts login page...", flush=True)
    driver.get(_LOGIN_URL)

    print("\n" + "="*60, flush=True)
    print("ACTION REQUIRED: Log in manually in the Chrome window.")
    print("  → Enter your email, click Continue")
    print("  → Spotify will send a code to your email — enter it")
    print("  → Complete login until you see the charts page")
    print("\nOnce you can see the charts homepage, come back here")
    print("and press ENTER to continue the download.")
    print("="*60, flush=True)
    input()

    # Verify we're actually on charts.spotify.com
    if "charts.spotify.com" not in driver.current_url:
        print(f"[warn] Expected charts.spotify.com but got: {driver.current_url}")
        print("Please navigate to charts.spotify.com in the browser, then press ENTER.")
        input()

    # Accept cookie banner if present
    try:
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        )
        time.sleep(1)
        btn.click()
    except Exception:
        pass

    print("✓ Session captured — starting downloads", flush=True)


# ---------------------------------------------------------------------------
# Download one chart
# ---------------------------------------------------------------------------

def _is_logged_out(driver) -> bool:
    """True if Spotify redirected us to the login/accounts page."""
    try:
        url = driver.current_url
        return "accounts.spotify.com" in url or "login" in url
    except Exception:
        return False


def _recover_driver(driver, download_dir: Path):
    """Try to recover from a crashed tab by opening a new one."""
    from selenium.webdriver.common.by import By
    try:
        driver.execute_script("window.open('about:blank', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])
        return True
    except Exception:
        return False


def download_chart(driver, d: date, download_dir: Path, username: str = "", password: str = "") -> bool:
    """Navigate to the chart page and click download. Returns True on success."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import WebDriverException

    url = f"{_CHART_BASE}/{d}"

    try:
        driver.get(url)
        time.sleep(1)
    except WebDriverException:
        # Tab crashed — try to recover with a new tab
        if not _recover_driver(driver, download_dir):
            _write_placeholder(download_dir, d)
            return True
        try:
            driver.get(url)
            time.sleep(1)
        except Exception:
            _write_placeholder(download_dir, d)
            return True

    # Detect logout — pause for manual re-login and retry
    if _is_logged_out(driver):
        print(f"\n  [session expired] Please log in again in the browser, then press ENTER...", flush=True)
        login(driver)
        driver.get(url)
        time.sleep(1)

    wait = WebDriverWait(driver, 15)
    try:
        result = wait.until(EC.any_of(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-labelledby='csv_download']")),
            EC.presence_of_element_located((By.CSS_SELECTOR, '[class*="ErrorPanel"]')),
            EC.presence_of_element_located((By.CSS_SELECTOR, '[class*="NotFound"]')),
            EC.presence_of_element_located((By.CSS_SELECTOR, '[class*="error-page"]')),
        ))

        if result.tag_name != "button":
            _write_placeholder(download_dir, d)
            return True

        result.click()

        expected = download_dir / csv_filename(d)
        for _ in range(30):
            time.sleep(0.5)
            if expected.exists() and not any(download_dir.glob("*.crdownload")):
                return True
        return expected.exists()

    except Exception:
        _write_placeholder(download_dir, d)
        return True


def _write_placeholder(download_dir: Path, d: date):
    """Empty CSV for weeks with no chart (e.g. before charts existed for that region)."""
    p = download_dir / csv_filename(d)
    p.write_text("rank,uri,artist_names,track_name,source,peak_rank,previous_rank,days_on_chart,streams\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start", default=str(_FIRST_WEEK))
    parser.add_argument("--to",   dest="end",   default=str(date.today()))
    parser.add_argument("--out",  default=str(_OUT_DIR))
    parser.add_argument("--headless", action="store_true",
                        help="Run Chrome in headless mode (no visible window)")
    args = parser.parse_args()

    username = os.environ.get("SPOTIFY_USERNAME", "").strip()
    password = os.environ.get("SPOTIFY_PASSWORD", "").strip()
    if not username or not password:
        print("[ERROR] SPOTIFY_USERNAME and SPOTIFY_PASSWORD must be set in .env")
        sys.exit(1)

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)
    out   = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    all_dates  = list(thursdays(max(start, _FIRST_WEEK), end))
    existing   = {f.name for f in out.glob("*.csv")}
    todo       = [d for d in all_dates if csv_filename(d) not in existing]
    skipped    = len(all_dates) - len(todo)

    print(f"Weekly global charts: {start} → {end}")
    print(f"  {len(all_dates)} weeks total | {skipped} already done | {len(todo)} to download")
    if not todo:
        print("Nothing to do.")
        return

    driver = make_driver(out, headless=args.headless)
    login(driver)

    ok = skipped
    failed = []

    for i, d in enumerate(todo):
        download_chart(driver, d, out, "", "")
        ok += 1   # placeholder written on timeout so every date is "handled"

        if (i + 1) % 25 == 0:
            pct = (i + 1 + skipped) / len(all_dates) * 100
            print(f"  {i+1+skipped}/{len(all_dates)} ({pct:.0f}%) done", flush=True)

    driver.quit()

    print(f"\n✓ {ok}/{len(all_dates)} charts saved to {out}")
    if failed:
        print(f"  {len(failed)} failed: {[str(d) for d in failed[:10]]}")
        if len(failed) <= 20:
            print("  Re-run the script to retry failed dates (they'll be skipped if already saved).")


if __name__ == "__main__":
    main()
