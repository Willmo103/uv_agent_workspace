import json
from pathlib import Path

FETCHED_PAGES = Path("~/fetched_webpages").expanduser()

if not FETCHED_PAGES.exists():
    FETCHED_PAGES.mkdir(parents=True, exist_ok=True)

DESCRIBED_FILES = Path("~/described_files").expanduser()

if not DESCRIBED_FILES.exists():
    DESCRIBED_FILES.mkdir(parents=True, exist_ok=True)

WEB_DESCRIPTION_CACHE_FILE = FETCHED_PAGES / "description_cache.json"
if not WEB_DESCRIPTION_CACHE_FILE.exists():
    WEB_DESCRIPTION_CACHE_FILE.write_text(json.dumps("{}", indent=2), encoding="utf-8")
