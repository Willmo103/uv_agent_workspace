from pathlib import Path

FETCHED_PAGES = Path("~/fetched_webpages").expanduser()

if not FETCHED_PAGES.exists():
    FETCHED_PAGES.mkdir(parents=True, exist_ok=True)
