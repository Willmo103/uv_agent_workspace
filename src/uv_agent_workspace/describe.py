from typing import Optional

import typer

from .config import CLIENT, DESCRIBED_FILES, Path, PERCICE_MODEL


def _get_paths(path: str) -> tuple[Path, str]:
    """Return the directory Path and filename for a given file path.
    The directory is determined by the DESCRIBED_FILES directory and the file path, with slashes replaced by dots.
    The filename is the name of the file being described.
    """
    target = Path(path)
    if not target.is_absolute():
        target = target.resolve()
    dir_path = DESCRIBED_FILES / (
        target.as_posix().replace("/", ".").replace("\\", ".")
    )
    filename = target.name + ".description.txt"

    return dir_path, filename


def store_description(path: str, description: str):
    """Store the generated description in a text file for later retrieval."""
    dir_path, filename = _get_paths(path)
    if not dir_path.exists():
        dir_path.mkdir(parents=True, exist_ok=True)
    description_file = dir_path / filename
    description_file.write_text(description, encoding="utf-8")


def get_description(path: str) -> Optional[str]:
    """Retrieve the stored description for a given file path, if it exists."""
    dir_path, filename = _get_paths(path)
    description_file = dir_path / filename
    if description_file.exists():
        return description_file.read_text(encoding="utf-8")
    return None


def list_described_files(links: bool = False) -> dict[str, list[str]]:
    """List all files that have been described, organized by their directory."""
    described_files = {}

    for entry in DESCRIBED_FILES.iterdir():
        if entry.is_dir():
            descriptions = []
            for file in entry.iterdir():
                if file.suffix == ".description.txt":
                    if links:
                        original_path = file.stem.replace(".description", "").replace(
                            ".", "/"
                        )
                        descriptions.append(
                            f"[{file.stem.replace('.description', '')}]({original_path})"
                        )
                    else:
                        descriptions.append(file.stem.replace(".description", ""))
            described_files[entry.name] = descriptions
    return described_files


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
    description = get_description(path)
    if description:
        return description
    prompt = description_prompt(path, reason, content)
    response = CLIENT.chat(
        PERCICE_MODEL, [{"role": "user", "content": prompt}], think="low"
    )
    resp_text = response.message.content.strip()
    store_description(path, resp_text)
    return response.message.content.strip()


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
    described_files = list_described_files(links)
    if not described_files:
        print("No files have been described yet.")
        return
    for dir_name, files in described_files.items():
        print(f"Directory: {dir_name}")
        for file in files:
            print(f"  - {file}")
