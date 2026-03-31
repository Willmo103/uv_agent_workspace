"""Fetch HTML from web URLs and convert to markdown."""

import sys

import httpx
from html2text import HTML2Text
from urllib.parse import urlparse
import os

from .config import WATCH_DIR


def clean_url_path(url: str) -> str:
    """Extract base filename from URL, removing query params and fragments."""
    base_url = urlparse(url)
    return base_url.netloc.replace(".", "_") + base_url.path.replace("/", "_")


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


def main(url):
    """Fetch page, save as HTML and convert to markdown."""
    clean_name = clean_url_path(url)
    output_dir = WATCH_DIR / clean_name
    os.makedirs(output_dir, exist_ok=True)

    print(f"Fetching: {url}")

    html_content = fetch_url(url)
    html_path = os.path.join(output_dir, clean_name + ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Saved HTML: {html_path}")

    md_content = convert_to_markdown(html_content)
    md_path = os.path.join(output_dir, clean_name + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Saved markdown: {md_path}")

    lines = len(md_content.splitlines())
    print(f"Converted to {lines} lines of markdown")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
