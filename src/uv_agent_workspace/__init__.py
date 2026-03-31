from .watch import main as watch_main
from .fetch import main as web_fetch_main


def watch():
    """Start the directory watcher."""
    watch_main()


def fetch(url):
    """Fetch a webpage and convert to markdown."""
    web_fetch_main(url)
