import json
from pathlib import Path
import ollama

FETCHED_PAGES = Path("~/fetched_webpages").expanduser()
DESCRIBED_FILES = Path("~/described_files").expanduser()
APP_DATA = Path("~/.uv_agent").expanduser()

for directory in [FETCHED_PAGES, DESCRIBED_FILES, APP_DATA]:
    if not directory.exists():
        directory.mkdir(parents=True, exist_ok=True)

WEB_DESCRIPTION_CACHE_FILE = FETCHED_PAGES / "description_cache.json"
if not WEB_DESCRIPTION_CACHE_FILE.exists():
    WEB_DESCRIPTION_CACHE_FILE.write_text(json.dumps("{}", indent=2), encoding="utf-8")

CLIENT = ollama.Client()
PERCICE_MODEL = "qwen3.5-agent"
SMALL_MODEL = "qwen3.5-small"
