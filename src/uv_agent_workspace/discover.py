import typer
from .config import PERCICE_MODEL, CLIENT, FETCHED_PAGES, get_local_time
from .imports import Path, Literal, BaseModel, datetime, Optional
from .describe import store_description
from .models import DescriptionEntry

_CURRENT_ROOT: str = ""
_CURRENT_FILES: list[str] = []
_CURRENT_DIRS: list[str] = []
_PATH_BEING_CONSIDERED: Optional[str] = None
_USER_SELECTED_ROOT: Optional[str] = None

class AgentMemory(BaseModel):
    id: Optional[int] = None
    timestamp: datetime
    memory: str

class IgnoredFile(BaseModel):
    file_path: str
    reason: str

def generate_tree_str():
    if not any([_CURRENT_ROOT, _CURRENT_FILES, _CURRENT_DIRS, _PATH_BEING_CONSIDERED, _USER_SELECTED_ROOT]):
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

**Part 2:**

When you feel ready, use the `add_agent_memory` tool to commit what you want to your
memory.
 - feel free to draw assumptions about the user and their preferences based on the files you have seen and described so far.
 - memories are searchable, and span across sessions, so consider how what you assume will evolve over time through exposure to more files and information about the user.

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
    relative_root = current_root.relative_to(base_root) if _USER_SELECTED_ROOT else _CURRENT_ROOT

    tree_str = generate_tree_str()
    return f"""
---
Current Time: {get_local_time().isoformat()}
Current Root (relative to user selected root): {relative_root}
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
    if
    try:
        content = Path(file_path).read_text(encoding="utf-8")
        return content[:500]
    except Exception as e:
        return f"Could not read file content: {e}"

def add_agent_memory(memory: str):
    """Add a memory to the agent's memory store."""
    entry = AgentMemory(timestamp=datetime.now(), memory=memory)
    # Store the memory in the database or a file
    # For simplicity, we'll just print it here
    print(f"Memory added: {entry.memory} at {entry.timestamp}")


def path_choice(choice: Literal["skip", "add"], reason: str) -> str:
    """
    Choose whether to skip describing the current file/directory.

    Args:
        choice: Literal["skip", "add"] - Choice to either skip current file/directory or add it to the knowledge graph.
        reason: str - Reason for the choice made.
    Returns:
        str: "skip" if the file/directory should be skipped, "add" if it should be added to the knowledge graph.
    """
    if choice == "skip":
        return "skip"
    elif choice == "add":
        return "add"
    else:
        raise ValueError("Invalid choice. Must be 'skip' or 'add'.")
