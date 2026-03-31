"""Fetch HTML from web URLs and convert to markdown."""

import httpx
from html2text import HTML2Text
from urllib.parse import urlparse
import os

import typer

from .config import WATCH_DIR


def clean_url_path(url: str) -> tuple[str, str]:
    """Extract base filename from URL, removing query params and fragments."""
    base_url = urlparse(url)
    dirname = base_url.netloc
    filename = base_url.path.strip("/").replace("/", "_") or "index"
    return dirname, filename


def fetch_url(url: str) -> str:
    """Fetch HTML content from given URL."""
    # disable SSL verification for Windows compatibility
    resp = httpx.get(url, timeout=30.0, verify=False)
    if resp.status_code == 200:
        return resp.text
    raise RuntimeError(f"HTTP {resp.status_code}: Failed to fetch {url}")


def convert_to_markdown(html: str) -> str:
    """Convert HTML to markdown using html2text."""
    parser = HTML2Text()
    return parser.handle(html).strip()


app = typer.Typer(help="Fetch a webpage and convert to markdown.")


@app.command()
def fetch(
    url=typer.Argument(
        ..., help="The URL of the webpage to fetch and convert to markdown."
    )
):
    dirname, filename = clean_url_path(url)
    output_dir = WATCH_DIR / dirname
    os.makedirs(output_dir, exist_ok=True)

    print(f"Fetching: {url}")

    html_content = fetch_url(url)
    html_path = os.path.join(output_dir, filename + ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Saved HTML: {html_path}")

    md_content = convert_to_markdown(html_content)
    md_path = os.path.join(output_dir, filename + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Saved markdown: {md_path}")

    lines = len(md_content.splitlines())
    print(f"Converted to {lines} lines of markdown")


@app.command(name="list")
def list_fetched():
    """List all fetched webpages in the watch directory."""
    if not WATCH_DIR.exists():
        print(f"No fetched webpages found in {WATCH_DIR}")
        return

    print(f"Fetched webpages in {WATCH_DIR}:")
    for entry in WATCH_DIR.iterdir():
        if entry.is_dir():
            print(f"- {entry.name}")
            for desc in entry.glob("*.description.txt"):
                print(f"  - {desc.name}")


if __name__ == "__main__":
    app()
