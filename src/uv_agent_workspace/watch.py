import os
import time
import json

from .imports import Path
from .config import (
    FETCHED_PAGES,
    WEB_DESCRIPTION_CACHE_FILE,
    CLIENT,
    PERCICE_MODEL,
)

LOGFILE = FETCHED_PAGES / "watch_and_describe.log.jsonl"  # json list file
WEB_DESCRIPTION_CACHE = {}

try:
    with open(WEB_DESCRIPTION_CACHE_FILE, "r", encoding="utf-8") as f:
        WEB_DESCRIPTION_CACHE = json.load(f)
except Exception as e:
    print(f"Error loading description cache: {e}")
    WEB_DESCRIPTION_CACHE = {}
for f in FETCHED_PAGES.iterdir():
    if f.is_dir():
        for file in f.iterdir():
            if file.suffix == ".md":
                description_file = file.with_suffix(".description.txt")
                if description_file.exists():
                    if not WEB_DESCRIPTION_CACHE.get(file.as_posix()):
                        WEB_DESCRIPTION_CACHE[file.as_posix()] = (
                            description_file.read_text(encoding="utf-8").strip()
                        )
WEB_DESCRIPTION_CACHE_FILE.write_text(
    json.dumps(WEB_DESCRIPTION_CACHE, indent=2), encoding="utf-8"
)


def format_json_to_single_line(json_obj: dict) -> str:
    """Convert a JSON object to a single-line string."""

    return json.dumps(json_obj, separators=(",", ":"))


def append_to_logfile(entry: dict):
    """Append a JSON entry to the log file as a single line."""
    if not LOGFILE.exists():
        LOGFILE.touch()
    LOGFILE.write_text(
        format_json_to_single_line(entry), encoding="utf-8", newline="\n"
    )


def describe_prompt(content: str) -> str:
    """Format the prompt for the LLM based on the file path."""
    return f"""
# Webpage Content Description

You are very knowledgeable. An expert. Think and respond with confidence.

## Task

Describe the content of the webpage provided below in a concise manner; taking into account the type of information it contains,
and why the user might be wanting to store this information. For example, if the webpage is a news article,
the description might include the main topic of the article, the source, and any key details that stand out.
If the webpage is a piece of documentation, the description might focus on the subject matter, and specific topics covered e.g.
"This webpage contains documentation for the Python requests library, covering installation instructions, usage examples, and API reference.
If the webpage has a lot of data tables or structured information, the description might highlight the type of data and its potential use cases.
The goal is to provide a clear and concise summary that captures the essence of the webpage's content, and why it might be valuable to the user."

## Output Format

- The output should be 1400 characters or less
- The output should be formatted as a markdown string
- The output should be provided with retriveal in mind
- `Obsidian.MD` style tags e.g. `#news` `#documentation` `#data-table` should be used to highlight keywords, topics,
themes, stand-out details, and specific types of data contained in the webpage.
  - tags should be included in the description, and should be relevant to the content of the webpage.
  - The tags should help categorize the webpage for easy retrieval later on.

---

Webpage Content:
```
{content}
```
"""


def describe_webpage_content(file_path: Path) -> str:
    """Read webpage content from file and get description from LLM."""
    cache_hit = WEB_DESCRIPTION_CACHE.get(file_path.as_posix())
    if cache_hit:
        print(f"Cache hit for {file_path.as_posix()}")
        return cache_hit
    content = file_path.read_text(encoding="utf-8")
    prompt = describe_prompt(content)
    response = CLIENT.chat(PERCICE_MODEL, [{"role": "user", "content": prompt}])
    log_entry = format_json_to_single_line(response.model_dump_json())
    WEB_DESCRIPTION_CACHE[file_path.as_posix()] = response.message.content.strip()
    WEB_DESCRIPTION_CACHE_FILE.write_text(
        json.dumps(WEB_DESCRIPTION_CACHE, indent=2), encoding="utf-8"
    )
    append_to_logfile({"file_path": file_path.as_posix(), "response": log_entry})
    return response.message.content.strip()


def watch_for_new_md_files():
    """Continuously watch the directory for new markdown files and describe them."""

    print(f"Watching directory: {FETCHED_PAGES} for new markdown files...")
    try:
        while True:
            for filename in FETCHED_PAGES.iterdir():
                if not filename.is_dir():
                    continue
                else:
                    for file in filename.iterdir():
                        if file.suffix == ".md":
                            description_file = file.with_suffix(".description.txt")
                            if not description_file.exists():
                                print(f"New markdown file found: {file.as_posix()}")
                                description = describe_webpage_content(file)
                                description_file.write_text(
                                    description, encoding="utf-8"
                                )
                                print(
                                    f"Description saved to: {description_file.as_posix()}"
                                )

            time.sleep(10)  # check every 10 seconds
    except KeyboardInterrupt:
        print("Stopping directory watch.")


def process_existing_md_files():
    """Process any existing markdown files in the directory on startup."""
    for filename in FETCHED_PAGES.iterdir():
        if not filename.is_dir():
            continue
        else:
            for file in filename.iterdir():
                if file.suffix == ".md":
                    description_file = file.with_suffix(".description.txt")
                    if not description_file.exists():
                        print(f"Processing existing markdown file: {file.as_posix()}")
                        description = describe_webpage_content(file)
                        description_file.write_text(description, encoding="utf-8")
                        print(f"Description saved to: {description_file.as_posix()}")


def main():
    """Main function to start watching the directory."""
    PROCESS_PID = os.getpid()
    _PID_FILE = FETCHED_PAGES / "watch_process.pid"
    if _PID_FILE.exists():
        existing_pid = _PID_FILE.read_text(encoding="utf-8").strip()
        if existing_pid:
            print(
                f"Another instance of the watcher is already running with PID: {existing_pid}. Exiting."
            )
            # terminate the existing process if it's still running
            try:
                os.kill(int(existing_pid), 0)  # check if process is running
                print(f"Terminating existing watcher process with PID: {existing_pid}")
                os.kill(int(existing_pid), 9)  # force kill
            except OSError:
                print(
                    f"No process found with PID: {existing_pid}. Continuing to start new watcher."
                )
    _PID_FILE.write_text(str(PROCESS_PID), encoding="utf-8")
    # the the running PID to the log file for monitoring purposes
    rettry_count = 0
    while rettry_count < 5:
        try:
            watch_for_new_md_files()
            break  # exit loop if successful
        except KeyboardInterrupt:
            print("Directory watch interrupted by user.")
            break
        except Exception as e:
            print(f"Error in main: {e}")
            append_to_logfile(
                format_json_to_single_line({"error": f"Error in main: {str(e)}"})
            )
            rettry_count += 1
            print(f"Retrying... ({rettry_count}/5)")
            if rettry_count >= 5:
                print("Max retry attempts reached. Exiting.")
                break
            else:
                continue  # retry immediately
        finally:
            _PID_FILE.unlink(missing_ok=True)  # clean up PID file on exit


if __name__ == "__main__":
    main()
