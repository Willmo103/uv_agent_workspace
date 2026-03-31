from fastapi import FastAPI
from .config import WATCH_DIR
from .fetch import convert_to_markdown, get_paths,


app = FastAPI()


app.post("/fetch")


def fetch(url: str, html: str):
    """Fetch a webpage and convert to markdown."""
    dirname, filename = get_paths(url)
    if not
    md_content = convert_to_markdown(html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="localhost", port=8756)
