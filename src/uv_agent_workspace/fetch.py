"""Fetch HTML from web URLs and convert to markdown."""

import httpx
from html2text import HTML2Text
from urllib.parse import urlparse
from bs4 import BeautifulSoup

import typer

from .config import FETCHED_PAGES, Path


def get_paths(url: str) -> tuple[Path, str]:
    """Return directory name and filename based on the URL."""
    base_url = urlparse(url)
    dirname = FETCHED_PAGES / base_url.netloc
    filename = base_url.path.strip("/").replace("/", "_") or "index"
    return dirname, filename


def extract_links_from_html(html: str) -> list[str]:
    """Extract all hyperlinks from the HTML content."""

    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a_tag in soup.find_all("a", href=True):
        links.append(a_tag["href"])
    return links


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


def should_update(existing_file: Path, new_content: str) -> bool:
    """returns True if the existing file needs to be updated based on content comparison."""
    if not existing_file.exists():
        return True
    existing_html = existing_file.read_text(encoding="utf-8")
    if existing_html == new_content:
        return False
    else:
        return True


app = typer.Typer(help="Fetch a webpage and convert to markdown.")


@app.command()
def fetch(
    url=typer.Argument(
        ..., help="The URL of the webpage to fetch and convert to markdown."
    )
):
    output_dir, filename = get_paths(url)
    html_file = output_dir / f"{filename}.html"
    md_file = output_dir / f"{filename}.md"
    output_dir.mkdir(parents=True, exist_ok=True)

    html_content = fetch_url(url)
    md_content = convert_to_markdown(html_content)
    if should_update(html_file, html_content):
        html_file.write_text(html_content, encoding="utf-8")
        md_file.write_text(md_content, encoding="utf-8")
        print(f"Fetched and saved: {url}")
    else:
        print(f"Skipped saving {url} since content is unchanged.")
    if should_update(md_file, md_content):
        md_file.write_text(md_content, encoding="utf-8")
        print(f"Markdown updated for: {url}")
    else:
        print(f"Skipped updating markdown for {url} since content is unchanged.")


@app.command(name="list")
def list_fetched():
    """List all fetched webpages in the watch directory."""
    if not FETCHED_PAGES.exists():
        print(f"No fetched webpages found in {FETCHED_PAGES}")
        return

    print(f"Fetched webpages in {FETCHED_PAGES}:")
    for entry in FETCHED_PAGES.iterdir():
        if entry.is_dir():
            print(f"- {entry.name}")
            for desc in entry.glob("*.description.txt"):
                print(f"  - {desc.name}")


if __name__ == "__main__":
    app()
