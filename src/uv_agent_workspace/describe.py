import typer

from .config import CLIENT, DESCRIBED_FILES, Path, MODEL


def store_description(path: str, description: str):
    """Store the generated description in a text file for later retrieval."""

    desc_file = DESCRIBED_FILES / f"{Path(path).stem}.file_description.txt"
    desc_file.write_text(description, encoding="utf-8")


def description_prompt(path: str, reason: str, content: str) -> str:
    """Generate a prompt for the LLM to describe file content."""
    return f"""
# File Content Description Agent

You are very knowledgeable. An expert. Think and respond with confidence.

## Task
Describe the content of a file in a concise manner, taking into account:
 - The reason the `discovery_agent` selected this file.
 - The Path of the file.
 - The content of the file.

## Output Format

- The output should be 1400 characters or less
- The output should be formatted as a markdown string
- The output should be provided with retriveal in mind
- `Obsidian.MD` style tags e.g. `#news` `#documentation` `#data-table` should be used to highlight keywords, topics,
themes, stand-out details, and specific types of data contained in the file.
  - tags should be included in the description, and should be relevant to the content of the file.
  - The tags should help categorize the file for easy retrieval later on.

---
**File Path*: `{path}`
**Reason for Selection*: `{reason}`
**File Content**:

```
{content}
```

"""


def describe_file_content(path: str, reason: str, content: str) -> str:
    """Generate a description for a file's content using the LLM."""
    prompt = description_prompt(path, reason, content)
    response = CLIENT.chat(MODEL, [{"role": "user", "content": prompt}])
    resp_text = response.message.content.strip()
    store_description(path, resp_text)
    return response.message.content.strip()


app = typer.Typer(help="Describe the content of a file using the LLM.")


@app.command()
def main(
    path: Path = typer.Argument(
        None,
        help="The path to the file to be described.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        callback=lambda p: Path(p).resolve(),
    ),
    reason: str = typer.Option(
        "User requested description",
        help="The reason why the file is being described (e.g., why it was selected by the discovery agent).",
    ),
):
    import rich
    from rich import markdown

    content = ""
    try:
        content = path.read_text(encoding="utf-8")
        description = describe_file_content(path.as_posix(), reason, content)
        md_desc = markdown.Markdown(description)
        rich.print(md_desc)
    except Exception as e:
        rich.print(f"Error reading file or generating description: {e}")
