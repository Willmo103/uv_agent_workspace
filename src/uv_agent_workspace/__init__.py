from .watch import main as watch_main
from .fetch import cmd as web_fetch_cmd


def watch():
    """Start the directory watcher."""
    watch_main()


def fetch(url):
    """Fetch a webpage and convert to markdown."""
    web_fetch_cmd()
