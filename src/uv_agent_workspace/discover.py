import json
from pathlib import Path

import typer

from uv_agent_workspace.config import FETCHED_PAGES

from .watch import CLIENT, MODEL


def get_system_prompt(root_path: str, summary: str = "", current_goal: str = "") -> str:
    """System prompt for discovering and describing important file content."""
    base = f"""
# Discovery Agent

You are an expert developer helping a user with ADHD locate and catalog specific python and markdown files.
You are exploring the directory: {root_path}

## Workflow
1. Use `ls_dir` to explore directories. It will tell you file sizes and if a file is already `[SELECTED]`.
2. Use `read_file` to peek at file contents (limited to 1000 chars by default).
3. Use `select_file` to catalog important python/markdown files with a reason. Do not select files that are already marked `[SELECTED]`.
4. Skip irrelevant directories (like .venv, __pycache__, node_modules, etc.) by simply not exploring them.
"""
    if summary or current_goal:
        base += f"""
## Current State & Goals
**Summary of Recent Actions:** {summary or "Just starting out."}
**Current Goal:** {current_goal or "Explore the root directory and find high-value python/markdown files."}
"""
    return base


def get_condensation_prompt() -> str:
    """Prompt used to ask the LLM to summarize the conversation and dictate the next goal."""
    return """
You are a context-manager for an autonomous agent.
Review the preceding conversation history of the agent's actions (tool calls, file reads, directory listings).

Please provide a JSON response with exactly two keys:
1. "summary": A brief, dense paragraph summarizing what directories the agent just explored and what it found.
2. "next_goal": A single sentence instructing the agent on what to explore or do next based on where it left off.
"""


class DiscoveryState:
    """Lightweight state manager to handle the synced JSON and path resolution."""

    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()
        safe_name = self.root_path.name
        self.json_path = FETCHED_PAGES / f"selected_files.{safe_name}.json"

        self.selected_files = {}
        if self.json_path.exists():
            try:
                self.selected_files = json.loads(
                    self.json_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                pass

    def save(self):
        """Sync the current selected files to disk."""
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        self.json_path.write_text(
            json.dumps(self.selected_files, indent=2), encoding="utf-8"
        )

    def _resolve(self, path: str) -> Path:
        """Resolve a path safely against the root."""
        target = Path(path)
        if not target.is_absolute():
            target = self.root_path / target
        return target.resolve()

    def ls_dir(self, path: str) -> str:
        """List directory contents, including file sizes and selection status."""
        target = self._resolve(path)
        if not target.exists() or not target.is_dir():
            return f"Error: {target} is not a valid directory."

        entries = []
        for entry in target.iterdir():
            if entry.is_dir():
                entries.append(f"[DIR]  {entry.name}/")
            else:
                size_kb = entry.stat().st_size / 1024
                status = (
                    " [SELECTED]" if entry.as_posix() in self.selected_files else ""
                )
                entries.append(f"[FILE] {entry.name} ({size_kb:.1f} KB){status}")

        return "\n".join(entries) if entries else "Empty directory."

    def read_file(self, path: str, length: int = 1000) -> str:
        """Read the content of a file, capped at `length` characters."""
        target = self._resolve(path)
        if not target.exists() or not target.is_file():
            return f"Error: {target} is not a valid file."

        try:
            content = target.read_text(encoding="utf-8")
            if len(content) > length:
                return content[:length] + f"\n...[TRUNCATED AT {length} CHARS]"
            return content
        except Exception as e:
            return f"Error reading file (might be binary): {e}"

    def select_file(self, path: str, reason: str) -> str:
        """Mark a file as important and sync to disk."""
        target = self._resolve(path)
        if not target.exists() or not target.is_file():
            return f"Error: {target} is not a valid file."

        target_posix = target.as_posix()
        self.selected_files[target_posix] = reason
        self.save()
        return f"Successfully selected {target_posix}. Reason saved."


def summarize_history(messages: list) -> tuple[str, str]:
    """Passes the recent history to the LLM to compress it into a summary and a new goal."""
    condensation_messages = messages.copy()
    condensation_messages.append(
        {"role": "system", "content": get_condensation_prompt()}
    )

    response = CLIENT.chat(MODEL, condensation_messages)

    try:
        # Assuming the LLM returns a raw JSON string or markdown JSON block
        content = (
            response.message.content.replace("```json", "").replace("```", "").strip()
        )
        data = json.loads(content)
        return data.get("summary", ""), data.get("next_goal", "")
    except Exception as e:
        print(f"Failed to parse condensation: {e}")
        return "Failed to summarize recent actions.", "Continue exploring."


def agent_loop(root_path: str):
    """Main execution loop for the agent."""
    state = DiscoveryState(root_path)

    tool_map = {
        "ls_dir": state.ls_dir,
        "read_file": state.read_file,
        "select_file": state.select_file,
    }

    summary = ""
    current_goal = ""

    # We use a mutable system message at index 0 so we can update it after condensation
    messages = [
        {
            "role": "system",
            "content": get_system_prompt(root_path, summary, current_goal),
        },
        {"role": "user", "content": f"Begin exploration of {root_path}."},
    ]

    turn_count = 0
    MAX_TURNS_BEFORE_CONDENSATION = 5  # Adjust based on your context window needs

    while True:
        response = CLIENT.chat(MODEL, messages, tools=list(tool_map.values()))

        if response.message.tool_calls:
            messages.append(response.message)

            for tool_call in response.message.tool_calls:
                func_name = tool_call.function.name
                func_args = tool_call.function.arguments

                print(f"Executing: {func_name}({func_args})")

                if func_name in tool_map:
                    result = tool_map[func_name](**func_args)
                else:
                    result = f"Error: Tool {func_name} missing."

                messages.append(
                    {
                        "role": "tool",
                        "name": func_name,
                        "content": str(result),
                    }
                )

            turn_count += 1

            # Condense history if it gets too long
            if turn_count >= MAX_TURNS_BEFORE_CONDENSATION:
                print("\n--- Condensing Context ---")
                summary, current_goal = summarize_history(messages)
                print(f"New Summary: {summary}\nNew Goal: {current_goal}\n")

                # Reset history: Keep the updated system prompt and the very last interaction
                messages = [
                    {
                        "role": "system",
                        "content": get_system_prompt(root_path, summary, current_goal),
                    },
                    messages[
                        -2
                    ],  # Keep the last tool execution result to maintain flow
                ]
                turn_count = 0

            continue

        else:
            print(f"\nAgent: {response.message.content}\n")
            messages.append({"role": "assistant", "content": response.message.content})

            # Optional: Ask the user for input here to steer the agent,
            # or auto-prompt it to keep going based on the current goal.
            user_input = input(
                "User (press enter to let agent continue, or type a command): "
            )
            if user_input.lower() in ["exit", "quit"]:
                break

            messages.append(
                {
                    "role": "user",
                    "content": user_input or "Continue with the current goal.",
                }
            )


app = typer.Typer(
    name="discover", help="Discover and catalog important files in a directory."
)


@app.command(name="start")
def main(
    root_path: str = typer.Argument(
        ...,
        help="The root directory to start discovery from.",
        show_default=True,
        exists=True,
        file_okay=False,
        dir_okay=True,
    )
):
    print(f"Starting Discovery Agent in {root_path}...")
    agent_loop(root_path)
