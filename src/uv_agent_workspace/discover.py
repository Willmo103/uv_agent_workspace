import json
from pathlib import Path
import typer

from uv_agent_workspace.config import FETCHED_PAGES

from .watch import CLIENT, MODEL


def discovery_sys_prompt(root_path: str) -> str:
    """System prompt for discovering and describing important file content in the watched directory."""
    return f"""
# Discovery Agent

You are very knowledgeable. An expert. Think and respond with confidence.

## Workflow

Each iteration you will use the tools to examine and select files and/or exclude paths in the current directory.
Files that have been removed from the directory tree by being selected or ignored will be removed from the list of
files in each turn to explore, and the agent will be able to focus on the remaining files.
The process will continue until there are no more paths left in the context to explore, meaning that the agent has either selected or ignored all paths in the directory.

## Tools
You have access to the following tools to help you explore and discover important content:

1. `read_file(path: str) -> str`: returns the content of the specified file path.
2. `change_directory(path: str) -> str`: change the current working directory to the specified path and return the new current directory.
3. `select_file(path: str, reason: str) -> str`: select a file that you think is important and relevant to the user.
   reason is a string that explains why you think this file is important and relevant to the user.
4. `ignore_path(path: str, reason: str) -> str`: ignore a file or directory that you think is not important and relevant to the user.
   reason is a string that explains why you think this file or directory is not important and relevant to the user. e.g `.venv` directories, `__pycache__` directories, log files, etc.

## User Intent
The user wants to know in general where specific python and markdown files are on his hard disk, and what they contain.
The user suffers from ADHD and has trouble keeping track of all the information he has, and where it is stored.
The user has asked you to explore the directory and find important content that may be relevant to him.
The process will be agent-guided discovery, where you will run inside of an infinite loop of exploring the directory
and discovering important content, and then asking the user if they want to know more about any of the content you have discovered.
"""


def build_tree_obj(path: Path) -> dict:
    """Build a tree object representing the directory structure starting from the given path."""
    tree = {}
    for entry in path.iterdir():
        if entry.is_dir():
            tree[entry.name] = build_tree_obj(entry)
        else:
            tree[entry.name] = None
    return tree


class AgentContext:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()
        self.current_path = self.root_path

        safe_path_name = self.root_path.as_posix().replace("/", "_")
        self._selected_files_json = (
            FETCHED_PAGES / f"selected_files.{safe_path_name}.json"
        )

        self.selected_files = {}
        if self._selected_files_json.exists():
            try:
                self.selected_files = json.loads(
                    self._selected_files_json.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                pass

        # Use "root" as the explicit top-level key to align with the update logic
        self.tree = {"root": build_tree_obj(self.root_path)}
        self.ignored_paths = set()

    def _filter_and_update_tree(self, removed_path: str):
        """Remove a path from the tree and update the tree structure accordingly."""
        try:
            # Get path parts relative to the root directory
            rel_path = Path(removed_path).resolve().relative_to(self.root_path)
        except ValueError:
            return  # Path is outside the root directory; nothing to remove

        def remove_path_from_tree(tree: dict, parts: tuple) -> bool:
            if not parts:
                return True  # Signal to remove this node

            current_part = parts[0]
            if current_part in tree:
                # If this is the last part, delete it
                if len(parts) == 1:
                    del tree[current_part]
                    return (
                        not tree
                    )  # Return True if the current directory becomes empty

                # If it's a sub-directory, recurse
                if isinstance(tree[current_part], dict):
                    should_remove = remove_path_from_tree(tree[current_part], parts[1:])
                    if should_remove:
                        del tree[current_part]
                        return not tree
            return False

        remove_path_from_tree(self.tree["root"], rel_path.parts)

    def _resolve_path(self, path: str) -> Path:
        """Helper to safely resolve a path against the current working directory."""
        target_path = Path(path)
        if not target_path.is_absolute():
            target_path = self.current_path / target_path
        return target_path.resolve()

    def list_directory(self, path: str) -> str:
        """List files and subdirectories in the specified directory path."""
        target_path = self._resolve_path(path)
        if not target_path.exists() or not target_path.is_dir():
            return f"Error: {target_path} is not a valid directory path."

        entries = []
        for entry in target_path.iterdir():
            entries.append(f"{entry.name}/" if entry.is_dir() else entry.name)
        return "\n".join(entries)

    def read_file(self, path: str) -> str:
        """Read the content of the specified file path."""
        target_path = self._resolve_path(path)
        if not target_path.exists() or not target_path.is_file():
            return f"Error: {target_path} is not a valid file path."
        return target_path.read_text(encoding="utf-8")

    def change_directory(self, path: str) -> str:
        """Change the current working directory to the specified path and return the new current directory."""
        target_path = self._resolve_path(path)
        if not target_path.exists() or not target_path.is_dir():
            return f"Error: {target_path} is not a valid directory path."

        self.current_path = target_path
        return self.current_path.as_posix()

    def select_file(self, path: str, reason: str) -> str:
        """Select a file that you think is important and relevant to the user."""
        target_path = self._resolve_path(path)
        if not target_path.exists() or not target_path.is_file():
            return f"Error: {target_path} is not a valid file path."

        target_posix = target_path.as_posix()
        self.selected_files[target_posix] = reason
        self._selected_files_json.write_text(
            json.dumps(self.selected_files, indent=2), encoding="utf-8"
        )
        self._filter_and_update_tree(
            target_posix
        )  # Remove selected file from exploration tree
        return f"Selected {target_posix} for the following reason: {reason}"

    def ignore_path(self, path: str, reason: str) -> str:
        """Ignore a file or directory that you think is not important and relevant to the user."""
        target_path = self._resolve_path(path)
        if not target_path.exists():
            return f"Error: {target_path} is not a valid path."

        target_posix = target_path.as_posix()
        self.ignored_paths.add(target_posix)
        self._filter_and_update_tree(
            target_posix
        )  # Remove ignored file from exploration tree
        return f"Ignored {target_posix} for the following reason: {reason}"

    def current_prompt(self) -> str:
        """Return the current system prompt for the agent based on the current context."""
        selected_files_str = (
            "\n".join(
                f"{path}: {reason}" for path, reason in self.selected_files.items()
            )
            or "None"
        )

        ignored_str = "\n".join(self.ignored_paths) or "None"

        remaining_keys = (
            "\n - ".join(self.tree["root"].keys())
            if self.tree["root"]
            else "No files left."
        )

        return f"""
# Discovery Agent Context

Current Directory: {self.current_path.as_posix()}

Selected Files:
{selected_files_str}

Ignored Files and Directories:
{ignored_str}

Current Directory Structure:
{remaining_keys}
"""


def agent_loop(root_path: str):
    """Main loop for the discovery agent."""
    context = AgentContext(root_path)

    # Map tool names to their actual functions for easy execution
    tool_map = {
        "list_directory": context.list_directory,
        "read_file": context.read_file,
        "change_directory": context.change_directory,
        "select_file": context.select_file,
        "ignore_path": context.ignore_path,
    }

    # Initialize the conversation history
    messages = [
        {"role": "system", "content": discovery_sys_prompt(root_path)},
        {"role": "user", "content": context.current_prompt()},
    ]

    while context.tree.get("root"):
        response = CLIENT.chat(
            MODEL,
            messages,
            tools=list(tool_map.values()),
        )

        # Check if the model wants to call one or more tools
        if response.message.tool_calls:
            # 1. Append the assistant's tool-call request to the history
            # (Most APIs require the assistant's original tool call message to be in the history)
            messages.append(response.message)

            # 2. Execute each tool and append the results as 'tool' messages
            for tool_call in response.message.tool_calls:
                func_name = tool_call.function.name
                func_args = tool_call.function.arguments

                print(f"Agent called {func_name} with args: {func_args}")

                try:
                    if func_name in tool_map:
                        result = tool_map[func_name](**func_args)
                    else:
                        result = f"Error: Tool {func_name} not found."
                except Exception as e:
                    result = f"Error executing tool: {e}"

                # Append the result of the local function execution back to the LLM
                messages.append(
                    {
                        "role": "tool",
                        "name": func_name,
                        "content": str(result),
                    }
                )

            # Continue the loop immediately so the LLM can read the tool results
            continue

        else:
            # The agent provided a standard text response instead of a tool call
            print(f"Agent Response:\n{response.message.content}")

            # Append the assistant's response to maintain conversation flow
            messages.append({"role": "assistant", "content": response.message.content})

            # Re-evaluate the context and prompt the agent to keep going
            # (This reflects the updated directory state after tools were run)
            messages.append({"role": "user", "content": context.current_prompt()})


app = typer.Typer()


@app.command(name="discover")
def main(
    root_path: str = typer.Argument(
        ...,
        help="The root directory path to start discovery from.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    )
):
    """Main function to start the discovery agent."""
    context = AgentContext(root_path)
    print("Starting Discovery Agent with the following context:")
    print(context.current_prompt())

    # Execute the loop (omitted from the original snippet but necessary for flow)
    agent_loop(root_path)
