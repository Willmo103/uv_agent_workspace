import ollama
import sqlite_utils
from .imports import Path, json, datetime, timezone


# determine the server tz
def get_local_time() -> datetime:
    """Get the local time with timezone information."""
    local_time = datetime.now().astimezone()
    print(f"Local time: {local_time}")
    return local_time


def get_utc_time() -> datetime:
    """Get the current UTC time."""
    utc_time = datetime.now(timezone.utc)
    print(f"UTC time: {utc_time}")
    return utc_time


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
GENERAL_MODEL = "qwen3.5-general"

DB = sqlite_utils.Database(APP_DATA / "uv_agent.db")
