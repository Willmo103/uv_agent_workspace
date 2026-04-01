import typer
from .config import DB, PERCICE_MODEL, CLIENT, get_local_time
from .imports import Path, Literal, BaseModel, datetime, Optional
from .describe import store_description
from .models import DescriptionEntry
from ollama import Message
_CURRENT_ROOT: str = ""
_CURRENT_FILES: list[str] = []
_CURRENT_DIRS: list[str] = []
_PATH_BEING_CONSIDERED: Optional[str] = None
_USER_SELECTED_ROOT: Optional[str] = None
_LAST_CHOICE: Optional[str] = None
_LAST_REASON: Optional[str] = None
_MESSAGE_HISTORY: list[dict] = []

class AgentMemory(BaseModel):
    id: Optional[int] = None
    timestamp: datetime
    memory: str


class IgnoredPathEntry(BaseModel):
    file_path: str
    reason: str


def store_memory_entry(entry: AgentMemory):
    """Store an agent memory entry in the database."""
    DB["agent_memories"].insert(entry.model_dump(), pk="id")


def get_recent_memories(limit: int = 10) -> list[AgentMemory]:
    """Retrieve recent agent memories from the database."""
    try:
        DB["agent_memories"].create_index("timestamp")
        memories = DB["agent_memories"].rows(order_by="timestamp DESC", limit=limit)
        return [AgentMemory(**memory) for memory in memories]
    except Exception:
        return []


def store_ignored_path(entry: IgnoredPathEntry):
    """Store an ignored path entry in the database."""
    DB["ignored_description_paths"].insert(entry.model_dump(), pk="file_path")


def is_path_ignored(path: str) -> bool:
    """Check if a path is in the ignored paths database."""
    try:
        DB["ignored_description_paths"].create_index("file_path")
        ignored_entry = DB["ignored_description_paths"].get(path)
        return ignored_entry is not None
    except Exception:
        return False


def generate_tree_str():
    if not any(
        [
            _CURRENT_ROOT,
            _CURRENT_FILES,
            _CURRENT_DIRS,
            _PATH_BEING_CONSIDERED,
            _USER_SELECTED_ROOT,
        ]
    ):
        return "No directory currently being explored."
    base_root = Path(_USER_SELECTED_ROOT)
    current_root = Path(_CURRENT_ROOT)
    relative_root = current_root.relative_to(base_root)
    tree_str = f"Current Root: {relative_root}\n"
    for dir in _CURRENT_DIRS:
        tree_str += f"  - {dir}/\n"
    for file in _CURRENT_FILES:
        file = Path(file)
        # display the file size in bytes
        file_size = file.stat().st_size
        if file.as_posix() == _PATH_BEING_CONSIDERED:
            tree_str += f"  - [CONSIDERING] {file.name} ({file_size} bytes)\n"
        else:
            tree_str += f"  - {file.name} ({file_size} bytes)\n"


DISCOVERY_GOAL = """
## Discovery Goal
- Discover files
  - Identify files of interest (markdown, source code, config files, documentation, images) in the chosen root directory
  - Limit ingestion of standard library files, dependencies, and other files that are not directly relevant to the user's own codebases and projects.
    e.g. avoid describing files in `node_modules`, `venv`, `__pycache__`, `dist-packages`, etc.
  - The user is a software developer with ADHD and creates many repositories and files but struggles to keep track of them all.
  - The user wants this team of agents to operate in the chosen root directories and build a knowledge graph via descriptions
    and tags for realevent directories and codebases they have created.
  - The user wants the agents to be decisive and selective in which files they choose to describe and add to the knowledge graph.
- Avoid Bloat
  - Avoid describing system files, non-utf8 encoded files, and other files that are not directly relevant to the user's own codebases, personal information, notes, or projects.
  - Avoid empty or near-empty files.
  - Skip directories quickly if they contain a large number of files that are not relevant to the user's own codebases and projects: e.g. `.config`, `.git`, `.conda`,
    `package-lock.json`, `node_modules`, `venv`, `__pycache__`, `dist-packages`, etc.

"""
# -- Prompts --


def reflection_prompt(last_path: str) -> str:
    current_time = get_local_time().isoformat()
    return f"""
---
current_time: {current_time}
last_path: {last_path}
---
# Phase 3: Reflect on actions taken and reasoning

## Task

**Part 1:**

Reflect on the actions taken and the reasoning behind those actions. Consider the following questions:
- Why did you choose to take the actions you did?
- What made you feel confident in those actions?
- How do those actions and the reasoning behind them relate to the overall discovery goal?
- How do you feel the choice you made will positively impact the user and their goals?

**Part 2:**

When you feel ready, use the `add_agent_memory` tool to commit what you want to your
memory.
 - feel free to draw assumptions about the user and their preferences based on the files you have seen and described so far.
 - memories are searchable, and span across sessions, so consider how what you assume will evolve over time through exposure to more files and information about the user.

## Note

These 2 parts are meant to be completed in one turn, and not meant to be separate responses.
The expected action is to call the think and then call the tool in the same turn.

"""


def choice_prompt(path: str) -> str:
    return f"""
# Phase 2: Make a choice about the file/directory

## Task

Use the `path_choice` tool to choose whether to skip describing the current file/directory or add it to the knowledge graph.

"""


def thinking_prompt() -> str:
    global _CURRENT_ROOT, _CURRENT_FILES, _CURRENT_DIRS, _PATH_BEING_CONSIDERED, _USER_SELECTED_ROOT
    base_root = Path(_USER_SELECTED_ROOT)
    current_root = Path(_CURRENT_ROOT)
    relative_root = (
        current_root.relative_to(base_root) if _USER_SELECTED_ROOT else _CURRENT_ROOT
    )

    tree_str = generate_tree_str()
    return f"""
---
Current Time: {get_local_time().isoformat()}
Current Root (relative to user selected root): {relative_root}
Last Action Taken: {_LAST_CHOICE if _LAST_CHOICE else "N/A"}
Reasoning Behind Last Action: {_LAST_REASON if _LAST_REASON else "N/A"}
---
# Phase 1: Consider the greater context

## Task

Use the file tree below to understand the greater context of the file currently being considered in order to determine
if you should add or ignore the file/directory.

- Think about which path is being considered, and it's potential relevance in the current root's context.
- Consider the types of files and directories in the current root, and how the path being considered relates to them.
- Consider the overall discovery goal and how the path being considered might relate to it.

## Tools

In order to further aid you in your decision, you can use the `preview_file_content` tool to see a brief preview of the content of the file being considered.

## Current File Tree Context

```
{tree_str}
```

"""


# -- Tools --


def preview_file_content(file_path: str) -> str:
    """Preview the content of a file, limited to the first 500 characters."""
    if not Path(file_path).exists():
        return "File does not exist."
    if not Path(file_path).is_file():
        return "Path is not a file."
    try:
        content = Path(file_path).read_text(encoding="utf-8")
        return content[:500]
    except Exception as e:
        return f"Could not read file content: {e}"


def add_agent_memory(memory: str):
    """
    Add a memory to the agent's memory store.

    Args:
        memory: str - The memory content to be stored.
    Returns:
        str: Confirmation message that the memory has been added.
    """
    entry = AgentMemory(timestamp=datetime.now(), memory=memory)
    store_memory_entry(entry)

    return f"Memory added at {entry.timestamp}"


def path_choice(choice: Literal["skip", "add"], reason: str) -> str:
    """
    Choose whether to skip describing the current file/directory.

    Args:
        choice: Literal["skip", "add"] - Choice to either skip current file/directory or add it to the knowledge graph.
        reason: str - Reason for the choice made.
    Returns:
        str: "skip" if the file/directory should be skipped, "add" if it should be added to the knowledge graph.
    """
    global _LAST_CHOICE, _LAST_REASON
    if choice == "skip":
        entry = IgnoredPathEntry(
            file_path=Path(_PATH_BEING_CONSIDERED).as_posix(), reason=reason
        )
        DB["ignored_description_paths"].insert(entry.model_dump(), pk="file_path")
        _LAST_CHOICE = "skip"
        _LAST_REASON = reason
        return "skip"
    elif choice == "add":
        entry = DescriptionEntry(
            file_path=Path(_PATH_BEING_CONSIDERED).as_posix(),
            reason=reason,
            description=None,
        )
        store_description(entry)
        _LAST_CHOICE = "add"
        _LAST_REASON = reason
        return "add"
    else:
        raise ValueError("Invalid choice. Must be 'skip' or 'add'.")


def view_memories(limit: int = 10) -> str:
    """
    List all memories stored in the agent's memory store.

    Args:
        limit: int - The maximum number of memories to return.
        Default is 10.

    Returns:
        str: A formatted string of all memories.
    """
    memories = get_recent_memories(limit)
    if not memories:
        return "No memories found."
    memory_str = "Agent Memories:\n"
    for memory in memories:
        memory_str += (
            f"---\n Timestamp: {memory.timestamp}\n Memory:\n ```{memory.memory}```\n"
        )
    return memory_str


LOOP_STEPS = ["think", "act", "reflect"]
app = typer.Typer()

def main():

    global _CURRENT_ROOT, _CURRENT_FILES, _CURRENT_DIRS, _PATH_BEING_CONSIDERED, _USER_SELECTED_ROOT
    # Step 1: Get user input for root directory
    _USER_SELECTED_ROOT = typer.prompt("Enter the root directory to explore")
    if not Path(_USER_SELECTED_ROOT).exists():
        typer.echo("Directory does not exist. Exiting.")
        return
    if not Path(_USER_SELECTED_ROOT).is_dir():
        typer.echo("Path is not a directory. Exiting.")
        return

    # Step 2: Walk the directory tree and populate current files and directories
    for root, dirs, files in Path(_USER_SELECTED_ROOT).rglob("*"):
        _CURRENT_ROOT = root.as_posix()
        _CURRENT_DIRS = [dir.as_posix() for dir in dirs]
        _CURRENT_FILES = [file.as_posix() for file in files]

        # For each file and directory, consider whether to add it to the knowledge graph or skip it
        for path in _CURRENT_DIRS + _CURRENT_FILES:
            _PATH_BEING_CONSIDERED = path
            if is_path_ignored(path):
                continue

            for step in LOOP_STEPS:
