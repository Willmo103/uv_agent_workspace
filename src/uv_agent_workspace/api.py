from fastapi import FastAPI
from .fetch import process_html_content


app = FastAPI()


@app.post("/fetch")
def fetch(url: str, html: str):
    """Fetch a webpage and convert to markdown."""
    response = process_html_content(url, html)
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="localhost", port=8756)
