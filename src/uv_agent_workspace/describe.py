from uv_agent_workspace.watch import CLIENT, MODEL


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
    return response.message.content.strip()


def main(path: str):
    import rich
