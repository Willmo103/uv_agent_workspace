"""Fetch HTML from web URLs and convert to markdown."""

from .imports import Literal, Optional

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


def extract_links_from_html(html: str, base_url: Optional[str] = None) -> list[str]:
    """Extract all hyperlinks from the HTML content."""

    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a_tag in soup.find_all("a", href=True):
        if "https://" in a_tag["href"] or "http://" in a_tag["href"]:
            links.append(a_tag["href"])
        if base_url and a_tag["href"].startswith("/"):
            links.append(base_url + a_tag["href"])
    return links


def has_same_base_url(url1: str, url2: str) -> bool:
    """Check if two URLs have the same base URL (scheme + netloc)."""
    parsed1 = urlparse(url1)
    parsed2 = urlparse(url2)
    return (parsed1.scheme, parsed1.netloc) == (parsed2.scheme, parsed2.netloc)


def get_relative_links(base_url: str, links: list[str]) -> list[str]:
    """Filter links to include only those that are relative to the base URL."""
    relative_links = []
    for link in links:
        if has_same_base_url(base_url, link):
            relative_links.append(link)
    return relative_links


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


def page_mapping() -> dict[str, list[str]]:
    """Return a mapping of fetched pages with their descriptions and links."""
    mapping = {}
    if not FETCHED_PAGES.exists():
        return mapping

    for entry in FETCHED_PAGES.iterdir():
        if entry.is_dir():
            entries = []
            for file in entry.iterdir():
                if file.suffix == ".md":
                    entries += [file.stem]
            mapping[entry.name] = entries
    return mapping


def list_all_links() -> list[str]:
    mapping = page_mapping()
    fetched_sites = []
    for k in mapping:
        base_url = f"https://{k}"
        for entry in mapping[k]:
            path = entry.replace("_", "/")
            full_url = f"{base_url}/{path}"
            fetched_sites.append(full_url)
    return fetched_sites


def get_files(type: Literal["html", "markdown", "description"]) -> list[Path]:
    """Return a list of files of the specified type in the fetched pages directory."""
    suffix_map = {
        "html": ".html",
        "markdown": ".md",
        "description": ".description.txt",
    }
    suffix = suffix_map[type]
    files = []
    if not FETCHED_PAGES.exists():
        return files

    for entry in FETCHED_PAGES.iterdir():
        if entry.is_dir():
            for file in entry.iterdir():
                if file.suffix == suffix:
                    files.append(file)
    return files


def process_html_content(
    url: str,
    html: Optional[str] = None,
) -> dict[str, str]:
    """Process HTML content to extract markdown and links."""
    if html is None:
        html = fetch_url(url)
    output_dir, filename = get_paths(url)
    md_content = convert_to_markdown(html)
    resp = {}

    if should_update(output_dir / f"{filename}.html", html):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{filename}.html").write_text(html, encoding="utf-8")
        resp["html"] = f"Fetched and saved: {url}"
    else:
        resp["html"] = f"Skipped saving {url} since content is unchanged."
    if should_update(output_dir / f"{filename}.md", md_content):
        (output_dir / f"{filename}.md").write_text(md_content, encoding="utf-8")
        resp["markdown"] = f"Markdown updated for: {url}"
    else:
        resp["markdown"] = (
            f"Skipped updating markdown for {url} since content is unchanged."
        )
    return resp


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
        print(f"Fetched and saved: {url}")
    else:
        print(f"Skipped saving {url} since content is unchanged.")
    if should_update(md_file, md_content):
        md_file.write_text(md_content, encoding="utf-8")
        print(f"Markdown updated for: {url}")
    else:
        print(f"Skipped updating markdown for {url} since content is unchanged.")


@app.command(name="list")
def list_fetched(
    links: bool = typer.Option(
        False, "--links", help="List all links found in the fetched HTML files."
    )
):
    """List all fetched webpages in the watch directory."""
    if links:
        all_links = list_all_links()
        print("Links found in fetched webpages:")
        for link in all_links:
            print(f"- {link}")
        return
    mapping = page_mapping()
    if not mapping:
        print("No fetched webpages found.")
        return
    for k in mapping:
        print(f"{k}:")
        for entry in mapping[k]:
            print(f"  - {entry}")


@app.command(name="links")
def list_links(
    url: Optional[str] = typer.Argument(None, help="The URL to extract links from."),
    rel: bool = typer.Option(
        False,
        "-r",
        "--relative",
        help="List only links that are relative to the base URL.",
    ),
):
    """List all links found in the fetched HTML file for the given URL."""

    chosen_url = url if url else None
    while not chosen_url:
        urls = {i: link for i, link in enumerate(list_all_links())}
        if not urls:
            print("No fetched webpages found. Please fetch a webpage first.")
            return
        for i, link in urls.items():
            print(f"{i}: {link}")
        url_input = typer.prompt(
            "Enter the number of the URL to extract links from (or 'list' to see URLs again)"
        )
        if url_input.lower() == "list":
            continue
        try:
            url_index = int(url_input)
            if url_index in urls:
                chosen_url = urls[url_index]
            else:
                print("Invalid number. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number or 'list'.")
    html_file = get_paths(chosen_url)[0] / f"{get_paths(chosen_url)[1]}.html"
    if not html_file.exists():
        print(f"No HTML file found for {chosen_url}. Please fetch the webpage first.")
        return
    html_content = html_file.read_text(encoding="utf-8")
    links = extract_links_from_html(html_content, chosen_url)
    if not links:
        print(f"No links found in the HTML file for {chosen_url}.")
        return
    print(f"Links found in {chosen_url}:")
    for link in links:
        print(f"- {link}")


if __name__ == "__main__":
    app()
