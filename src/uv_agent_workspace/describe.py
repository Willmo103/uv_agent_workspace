import typer

from .imports import Optional
from .models import DescriptionEntry
from .config import CLIENT, Path, SMALL_MODEL, DB


def store_description(entry: DescriptionEntry):
    """Store a file description in the DESCRIBED_FILES directory."""
    DB["file_descriptions"].insert(entry.model_dump(), pk="file_path")


def retrieve_file_description(file_path: str) -> Optional[str]:
    """Retrieve a file description from the database."""
    try:
        entry = DB["file_descriptions"].rows_where("file_path = ?", [file_path])
        for e in entry:
            return e["description"]
        return None
    except Exception:
        return None


def get_file_description_tree(links: bool = False) -> dict[str, list[str]]:
    """Return a tree of described files organized by directory, optionally including clickable links."""
    entries = DB["file_descriptions"].rows
    tree = {}
    for entry in entries:
        path = Path(entry["file_path"])
        dir_name = path.parent.name
        file_name = path.name
        if dir_name not in tree:
            tree[dir_name] = []
        if links:
            tree[dir_name].append(f"[{file_name}]({entry['file_path']})")
        else:
            tree[dir_name].append(file_name)
    return tree


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

- The output should be 1500 characters or less.
- The output should be formatted as **markdown**.
- The output should be provided with retriveal in mind.
- `Obsidian.MD` style tags e.g. `#config` `#documentation` `#data-table` should be used to highlight keywords, topics,
themes, stand-out details, and specific types of data contained in the file.
  - Tags should be included in the description, and should be relevant to the content of the file.
  - Keep in mind that tags help categorize the file for easy retrieval later on.

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
    try:
        description = retrieve_file_description(path)
        if description:
            return description
    except Exception as e:
        print(f"Error retrieving description from database: {e}")
    prompt = description_prompt(path, reason, content)
    try:

        response = CLIENT.chat(
            SMALL_MODEL, [{"role": "user", "content": prompt}], think=True
        )
        resp_text = response.message.content.strip()
        entry = DescriptionEntry(file_path=path, reason=reason, description=resp_text)
        store_description(entry)
        return response.message.content.strip()
    except Exception as e:
        print(f"Error generating description from LLM: {e}")
        return "Failed to generate description."


app = typer.Typer(help="Describe the content of a file using the LLM.")


@app.command(name="get")
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


@app.command(name="ls")
def list_described(
    links: bool = typer.Option(
        False,
        "--links",
        help="List all described files with links to their original paths.",
    )
):
    described_files = get_file_description_tree(links)
    if not described_files:
        print("No files have been described yet.")
        return
    for dir_name, files in described_files.items():
        print(f"Directory: {dir_name}")
        for file in files:
            print(f"  - {file}")
