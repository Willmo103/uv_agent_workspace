from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .fetch import process_html_content


app = FastAPI()


@app.get("/")
def read_root():
    """Root endpoint."""
    return {"message": "Welcome to the UV Agent Workspace API!"}


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/fetch")
def fetch(url: str, html: str):
    """Fetch a webpage and convert to markdown."""
    response = process_html_content(url, html)
    return JSONResponse(content=response)


def main():
    """Main function to start the API server."""
    import uvicorn

    uvicorn.run(app, host="localhost", port=8756)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="localhost", port=8756)
