import json
from pathlib import Path

from uv_agent_workspace.config import FETCHED_PAGES

from .watch import CLIENT, MODEL


def discovery_sys_prompt(root_path: str) -> str:
    """System prompt for discovering and describing important file_content in the watched directory."""
    return f"""
# Discovery Agent

You are very knowledgeable. An expert. Think and respond with confidence.

## Workflow

Each iteration you will use the tools to examine and select files and/or exclude paths in the current directory.
files that have been removed from the directory tree by being selected or ignored will be removed from the list of
files in each turn to explore, and the agent will be able to focus on the remaining files.
The process will continue until there are no more paths left in the context to explore, meaning that the agent has either selected or ignored all paths in the directory.

## Tools
You have access to the following tools to help you explore and discover important content:

1. `read_file(path: str) -> str`: returns the content of the specified file path.
2. `change_directory(path: str) -> str`: change the current working directory to the specified path and return the new current directory.
3.  `select_file(path: str, reason: str) -> str`: select a file that you think is important and relevant to the user.
reason is a string that explains why you think this file is important and relevant to the user.
4. `ignore_path(path: str, reason: str) -> str`: ignore a file or directory that you think is not important and relevant to the user.
reason is a string that explains why you think this file or directory is not important and relevant to the user. e.g `.venv` directories, `__pycache__` directories, log files, etc.

## User Intent
The user wants to know in general where specific python and markdown files are on his harddisk, and what they contain.
The user suffers from ADHD and has trouble keeping track of all the information he has, and where it is stored.
The user has asked you to explore the directory and find important content that may be relevant to him.
The process will be agent guided discovery, where you will run inside of an infinate loop of exploring the directory
and discovering important content, and then asking the user if they want to know more about any of the content you have discovered.


"""


def agent_loop(root_path: str):
    """Main loop for the discovery agent."""
    context = AgentContext(root_path)
    tree_has_keys_left = bool(context.tree["root"].keys())
    messages = [
        {"role": "system", "content": discovery_sys_prompt(root_path)},
        {"role": "user", "content": context.current_prompt()},
    ]
    while tree_has_keys_left:
        prompt = context.current_prompt()
        response = CLIENT.chat(
            MODEL,
            [
                {"role": "system", "content": discovery_sys_prompt(root_path)},
                {"role": "user", "content": prompt},
            ],
            tools=[
                context.list_directory,
                context.read_file,
                context.change_directory,
                context.select_file,
                context.ignore_path,
            ],
        )
        print(f"Agent Response:\n{response}")
        tree_has_keys_left = bool(context.tree["root"].keys())


def build_tree_obj(path: Path) -> dict:
    """Build a tree object representing the directory structure starting from the given path."""
    root = path.as_posix()
    tree = {root: {}}
    for entry in path.iterdir():
        key = entry.relative_to(path).as_posix()
        if entry.is_dir():
            tree[root][key] = build_tree_obj(entry)[entry.as_posix()]
        else:
            tree[root][key] = None
    return tree


class AgentContext:
    def __init__(self, root_path: str):
        self._selected_files_json = FETCHED_PAGES / "selected_files.{}.json".format(
            root_path.replace("/", "_")
        )
        if self._selected_files_json.exists():
            self.selected_files = json.loads(
                self._selected_files_json.read_text(encoding="utf-8")
            )
        self.tree = build_tree_obj(self.current_path)
        self.current_path = self.tree["root"]
        self.selected_files = {}
        self.ignored_paths = set()

    def _filer_and_update_tree(self, removed_path: str):
        """Remove a path from the tree and update the tree structure accordingly."""

        def remove_path_from_tree(tree: dict, path_parts: list[str]) -> bool:
            if not path_parts:
                return True  # Signal to remove this node
            current_part = path_parts[0]
            if current_part in tree:
                should_remove = remove_path_from_tree(
                    tree[current_part], path_parts[1:]
                )
                if should_remove:
                    del tree[current_part]
                    return not tree  # Remove this node if it's empty
            return False

        path_parts = removed_path.split("/")
        remove_path_from_tree(self.tree["root"], path_parts)

    def list_directory(self, path: str) -> str:
        """List files and subdirectories in the specified directory path."""
        target_path = Path(path)
        if not target_path.is_absolute():
            target_path = Path(self.current_path) / target_path
        if not target_path.exists() or not target_path.is_dir():
            return f"Error: {target_path} is not a valid directory path."
        entries = []
        for entry in target_path.iterdir():
            if entry.is_dir():
                entries.append(f"{entry.name}/")
            else:
                entries.append(entry.name)
        return "\n".join(entries)

    def read_file(self, path: str) -> str:
        """Read the content of the specified file path."""
        target_path = Path(path)
        if not target_path.is_absolute():
            target_path = Path(self.current_path) / target_path
        if not target_path.exists() or not target_path.is_file():
            return f"Error: {target_path} is not a valid file path."
        return target_path.read_text(encoding="utf-8")

    def change_directory(self, path: str) -> str:
        """Change the current working directory to the specified path and return the new current directory."""
        target_path = Path(path)
        if not target_path.is_absolute():
            target_path = Path(self.current_path) / target_path
        if not target_path.exists() or not target_path.is_dir():
            return f"Error: {target_path} is not a valid directory path."
        self.current_path = target_path.as_posix()
        return self.current_path

    def select_file(self, path: str, reason: str) -> str:
        """Select a file that you think is important and relevant to the user."""
        target_path = Path(path)
        if not target_path.is_absolute():
            target_path = Path(self.current_path) / target_path
        if not target_path.exists() or not target_path.is_file():
            return f"Error: {target_path} is not a valid file path."
        self.selected_files[target_path.as_posix()] = reason
        return f"Selected {target_path.as_posix()} for the following reason: {reason}"

    def ignore_path(self, path: str, reason: str) -> str:
        """Ignore a file or directory that you think is not important and relevant to the user."""
        target_path = Path(path)
        if not target_path.is_absolute():
            target_path = Path(self.current_path) / target_path
        if not target_path.exists():
            return f"Error: {target_path} is not a valid path."
        self.ignored_paths.add(target_path.as_posix())
        self._filer_and_update_tree(target_path.as_posix())
        return f"Ignored {target_path.as_posix()} for the following reason: {reason}"

    def current_prompt(self) -> str:
        """Return the current system prompt for the agent based on the current context."""
        selected_files_str = "\n".join(
            [f"{path}: {reason}" for path, reason in self.selected_files.items()]
        )
        return f"""
#  Discovery Agent Context

Current Directory: {self.current_path}
Selected Files:
{selected_files_str}

Ignored Files and Directories:
{"\n".join(self.ignored_paths)}

Current Directory Structure:
{"\n - ".join(self.tree["root"].keys())}

"""


def main(
    root_path: str,
):
    """Main function to start the discovery agent."""
    context = AgentContext(root_path)
    print("Starting Discovery Agent with the following context:")
    print(context.current_prompt())
