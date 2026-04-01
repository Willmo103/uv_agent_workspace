import os

import typer
from .config import DB, CLIENT, GENERAL_MODEL, get_local_time
from .imports import Path, Literal, BaseModel, datetime, Optional
from .describe import store_description
from .models import DescriptionEntry

_CURRENT_ROOT: str = ""
_CURRENT_FILES: list[str] = []
_CURRENT_DIRS: list[str] = []
_PATH_BEING_CONSIDERED: Optional[str] = None
_USER_SELECTED_ROOT: Optional[str] = None
_LAST_CHOICE: Optional[str] = None
_LAST_REASON: Optional[str] = None


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


def is_path_child_of_ignored(path: str) -> bool:
    """Check if a path is a child of any ignored paths in the database."""
    try:
        DB["ignored_description_paths"].create_index("file_path")
        ignored_paths = DB["ignored_description_paths"].rows()
        for entry in ignored_paths:
            ignored_path = entry["file_path"]
            if Path(path).resolve().is_relative_to(Path(ignored_path).resolve()):
                return True
        return False
    except Exception:
        return False


def generate_tree_str():
    global _CURRENT_ROOT, _CURRENT_FILES, _CURRENT_DIRS, _PATH_BEING_CONSIDERED, _USER_SELECTED_ROOT
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

    return tree_str


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


def reflection_prompt() -> str:
    global _PATH_BEING_CONSIDERED, _LAST_CHOICE, _LAST_REASON
    current_time = get_local_time().isoformat()
    return f"""
---
current_time: {current_time}
last_path: {_PATH_BEING_CONSIDERED if _PATH_BEING_CONSIDERED else "N/A"}
last_choice: {_LAST_CHOICE if _LAST_CHOICE else "N/A"}
reasoning: {_LAST_REASON if _LAST_REASON else "N/A"}
---
# Phase 3: Reflect on actions taken and reasoning

## Task

Reflect on the actions taken and the reasoning behind those actions. Consider the following questions:
- Why did you choose to take the actions you did?
- What made you feel confident in those actions?
- How do those actions and the reasoning behind them relate to the overall discovery goal?
- How do you feel the choice you made will positively impact the user and their goals?
Use the **`add_agent_memory`** tool to commit what you want to your
memory.
 - feel free to draw assumptions about the user and their preferences based on the files you have seen and described so far.
 - memories are searchable, and span across sessions, so consider how what you assume will evolve over time through exposure to more files and information about the user.

"""


def choice_prompt() -> str:
    return f"""
---
current_time: {get_local_time().isoformat()}
path_being_considered: {_PATH_BEING_CONSIDERED if _PATH_BEING_CONSIDERED else "N/A"}
---
# Phase 2: Act on the choce made in the thinking phase and apply the reasoning

## Task

Use the `path_choice` tool act on the choice you made in the thinking phase

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


def system_prompt():
    return f"""
## Discovery Agent Workflow

## Background Context
- You are running in a loop over a directory tree chosen by the user to walk for discovery of files and directories relevant to the user's projects, codebases, notes, and personal information.
- Each response from the user will fully instruct you on what actions are expected from you
  during each phase of the loop, as well as the tools available to you to complete those actions.

## Workflow

The discovery agent operates in a loop with 3 phases: think, act, and reflect over each path in the
directory tree until the entire tree has been walked. The expected workflow is as follows:
1. Think
  - In this phase, you will consider the current file/directory in the context of the current root and the overall discovery goal.
  - This phase is where the choice of whether to add the file/directory to the knowledge graph or skip it should be made, and the reasoning behind that choice should be fully fleshed out and explained.
2. Act
  - In this phase, you will use the tool `path_choice` to act on the choice you made in the thinking phase, and add the file/directory to the knowledge graph or skip it, and apply the reasoning you fleshed out in the thinking phase.
3. Reflect
  - In this phase, you will reflect on the choice you made and the reasoning behind it and add a memory to the agent's memory store with the details of the choice and reasoning.

(Repeat the loop for the next file/directory in the directory tree)

{DISCOVERY_GOAL}
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
    global _LAST_CHOICE, _LAST_REASON, _PATH_BEING_CONSIDERED
    if choice == "skip":
        entry = IgnoredPathEntry(
            file_path=Path(_PATH_BEING_CONSIDERED).as_posix(), reason=reason
        )
        DB["ignored_description_paths"].insert(entry.model_dump(), pk="file_path")
        _LAST_CHOICE = "skip"
        _LAST_REASON = reason
        return f"Path {_PATH_BEING_CONSIDERED} will be skipped."
    elif choice == "add":
        entry = DescriptionEntry(
            file_path=Path(_PATH_BEING_CONSIDERED).as_posix(),
            reason=reason,
            description=None,
        )
        store_description(entry)
        _LAST_CHOICE = "add"
        _LAST_REASON = reason
        return "Path {_PATH_BEING_CONSIDERED} will be added to the knowledge graph."
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
LOOP_TOOLS = {
    "think": [
        preview_file_content,
        view_memories,
    ],
    "act": [path_choice],
    "reflect": [add_agent_memory, view_memories],
}
LOOP_TOOL_NAMES = {
    "think": ["preview_file_content", "view_memories"],
    "act": ["path_choice"],
    "reflect": ["add_agent_memory", "view_memories"],
}
LOOP_REQUIRED_CALLS = {
    "think": [],
    "act": ["path_choice"],
    "reflect": ["add_agent_memory"],
}
app = typer.Typer()


def main(path: Optional[str] = None):
    __MESSAGE_HISTORY = []

    global _CURRENT_ROOT, _CURRENT_FILES, _CURRENT_DIRS, _PATH_BEING_CONSIDERED, _USER_SELECTED_ROOT
    _USER_SELECTED_ROOT = Path(path).resolve().as_posix() if path else None
    # Step 1: Get user input for root directory
    if not _USER_SELECTED_ROOT:
        _USER_SELECTED_ROOT = typer.prompt("Enter the root directory to explore")
    if not Path(_USER_SELECTED_ROOT).exists():
        typer.echo("Directory does not exist. Exiting.")
        return
    if not Path(_USER_SELECTED_ROOT).is_dir():
        typer.echo("Path is not a directory. Exiting.")
        return
    if __MESSAGE_HISTORY == []:
        __MESSAGE_HISTORY.append({"role": "system", "content": system_prompt()})
    # Step 2: Walk the directory tree and populate current files and directories
    for root, dirs, files in os.walk(_USER_SELECTED_ROOT):
        root_path = Path(root)
        _CURRENT_ROOT = root_path.as_posix()
        _CURRENT_DIRS = [(root_path / dir).as_posix() for dir in dirs]
        _CURRENT_FILES = [(root_path / file).as_posix() for file in files]

        # For each file and directory, consider whether to add it to the knowledge graph or skip it
        spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        def _spin(index: int) -> str:
            return spinner_frames[index % len(spinner_frames)]

        def _status(message: str, color=typer.colors.CYAN, icon: str = "•") -> None:
            typer.secho(f"{icon} {message}", fg=color, bold=True)

        candidate_paths = _CURRENT_DIRS + _CURRENT_FILES
        _status(
            f"Scanning {_CURRENT_ROOT} | {len(_CURRENT_DIRS)} dirs, {len(_CURRENT_FILES)} files",
            color=typer.colors.BRIGHT_BLUE,
            icon="📂",
        )

        for path_index, path in enumerate(candidate_paths, start=1):
            _PATH_BEING_CONSIDERED = path
            path_name = Path(path).name or path

            typer.secho("", fg=typer.colors.WHITE)
            _status(
                f"{_spin(path_index)} Considering [{path_index}/{len(candidate_paths)}]: {path_name}",
                color=typer.colors.BRIGHT_CYAN,
                icon="🔎",
            )
            typer.echo(f"   Path: {path}")

            if is_path_ignored(path) or is_path_child_of_ignored(path):
                _status(
                    f"Already ignored, skipping: {path_name}",
                    color=typer.colors.YELLOW,
                    icon="↷",
                )
                continue

            for step_index, step in enumerate(LOOP_STEPS, start=1):
                required_calls = LOOP_REQUIRED_CALLS[step][:]
                requirements_met = False

                while not requirements_met:
                    tools = LOOP_TOOLS[step]
                    tool_names = LOOP_TOOL_NAMES[step]
                    phase_icon = _spin(path_index + step_index)

                    _status(
                        f"{phase_icon} Phase [{step.upper()}] for {path_name}",
                        color=typer.colors.MAGENTA,
                        icon="⚙",
                    )

                    if step == "think":
                        prompt = thinking_prompt()
                        response = CLIENT.chat(
                            model=GENERAL_MODEL,
                            messages=__MESSAGE_HISTORY
                            + [{"role": "user", "content": prompt}],
                            tools=tools,
                            think=False,
                        )
                    elif step == "act":
                        prompt = choice_prompt()
                        response = CLIENT.chat(
                            model=GENERAL_MODEL,
                            messages=__MESSAGE_HISTORY
                            + [{"role": "user", "content": prompt}],
                            tools=tools,
                            think=False,
                        )
                    elif step == "reflect":
                        prompt = reflection_prompt()
                        response = CLIENT.chat(
                            model=GENERAL_MODEL,
                            messages=__MESSAGE_HISTORY
                            + [{"role": "user", "content": prompt}],
                            tools=tools,
                            think=False,
                        )

                    __MESSAGE_HISTORY.append({"role": "user", "content": prompt})
                    message = response.message

                    if getattr(message, "content", None):
                        preview = message.content.strip()
                        if preview:
                            typer.secho(
                                f"💬 {preview[:160]}{'...' if len(preview) > 160 else ''}",
                                fg=typer.colors.WHITE,
                            )

                    tool_calls = getattr(message, "tool_calls", None) or []
                    if tool_calls:
                        _status(
                            f"Executing {len(tool_calls)} tool call(s)",
                            color=typer.colors.BLUE,
                            icon="🛠",
                        )

                    for tool_call in tool_calls:
                        tool_name = tool_call.function.name
                        tool_args = tool_call.function.arguments or {}

                        typer.echo(f"   → {tool_name}({tool_args})")

                        if tool_name in tool_names:
                            tool_func = tools[tool_names.index(tool_name)]
                            try:
                                tool_result = tool_func(**tool_args)
                                typer.secho(
                                    f"   ✓ {tool_name}: {tool_result}",
                                    fg=typer.colors.GREEN,
                                )
                            except Exception as e:
                                tool_result = f"Tool {tool_name} failed: {e}"
                                typer.secho(
                                    f"   ✗ {tool_result}",
                                    fg=typer.colors.RED,
                                    bold=True,
                                )
                        else:
                            tool_result = f"Tool {tool_name} not found."
                            typer.secho(
                                f"   ! {tool_result}",
                                fg=typer.colors.RED,
                                bold=True,
                            )

                        __MESSAGE_HISTORY.append(
                            {
                                "role": "tool",
                                "name": tool_name,
                                "content": str(tool_result),
                            }
                        )

                        if tool_name in required_calls:
                            required_calls.remove(tool_name)

                    if getattr(message, "content", None):
                        __MESSAGE_HISTORY.append(
                            {"role": "assistant", "content": message.content}
                        )

                    requirements_met = not required_calls

                    if not requirements_met:
                        missing = ", ".join(required_calls)
                        _status(
                            f"Required tool call(s) still missing: {missing}",
                            color=typer.colors.YELLOW,
                            icon="⚠",
                        )
                        __MESSAGE_HISTORY.append(
                            {
                                "role": "system",
                                "content": (
                                    "You must use the following tools before proceeding: "
                                    f"{missing}"
                                ),
                            }
                        )

                _status(
                    f"Completed phase [{step.upper()}] for {path_name}",
                    color=typer.colors.GREEN,
                    icon="✔",
                )
                __MESSAGE_HISTORY.append(
                    {
                        "role": "system",
                        "content": system_prompt(),
                    }
                )

            _status(
                f"Finished decision loop for {path_name}",
                color=typer.colors.BRIGHT_GREEN,
                icon="✅",
            )
            _PATH_BEING_CONSIDERED = None


@app.command()
def run(path: Optional[str] = typer.Option(None, "--path", "-p")):
    typer.secho("🚀 Starting discovery agent", fg=typer.colors.BRIGHT_GREEN, bold=True)
    if path:
        typer.echo(f"   Initial path: {path}")
        main(path or "")
