# Custom Tools Documentation - Agno

## Overview

In production environments, custom tools are essential for agent functionality. Agno provides a flexible framework where any Python function can be used as a tool by an Agent.

**Core Principles:**
- Any Python function can serve as a tool
- Use the `@tool` decorator to modify pre/post-call behavior

---

## Basic Tool Creation

### Simple Function as Tool

Any Python function with proper documentation can be used directly:

```python
import json
import httpx
from agno.agent import Agent

def get_top_hackernews_stories(num_stories: int = 10) -> str:
    """
    Use this function to get top stories from Hacker News.

    Args:
        num_stories (int): Number of stories to return. Defaults to 10.

    Returns:
        str: JSON string of top stories.
    """
    # Fetch top story IDs
    response = httpx.get('https://hacker-news.firebaseio.com/v0/topstories.json')
    story_ids = response.json()

    # Fetch story details
    stories = []
    for story_id in story_ids[:num_stories]:
        story_response = httpx.get(f'https://hacker-news.firebaseio.com/v0/item/{story_id}.json')
        story = story_response.json()
        if "text" in story:
            story.pop("text", None)
        stories.append(story)
    return json.dumps(stories)

agent = Agent(tools=[get_top_hackernews_stories], markdown=True)
agent.print_response("Summarize the top 5 stories on hackernews?", stream=True)
```

---

## The `@tool` Decorator

### Key Features

- **`requires_confirmation=True`**: Requires user confirmation before execution
- **`requires_user_input=True`**: Requires user input before execution (use `user_input_fields` to specify fields)
- **`external_execution=True`**: Tool executes outside agent's control
- **`show_result=True`**: Show tool output in agent's response (default: True)
- **`stop_after_tool_call=True`**: Stop agent run after tool call
- **`tool_hooks`**: Run custom logic before and after tool call
- **`cache_results=True`**: Cache tool results to avoid repetition (configure with `cache_dir` and `cache_ttl`)

### Advanced Example

```python
import httpx
from agno.agent import Agent
from agno.tools import tool
from typing import Any, Callable, Dict

def logger_hook(function_name: str, function_call: Callable, arguments: Dict[str, Any]):
    """Hook function that wraps the tool execution"""
    print(f"About to call {function_name} with arguments: {arguments}")
    result = function_call(**arguments)
    print(f"Function call completed with result: {result}")
    return result

@tool(
    name="fetch_hackernews_stories",
    description="Get top stories from Hacker News",
    stop_after_tool_call=True,
    tool_hooks=[logger_hook],
    requires_confirmation=True,
    cache_results=True,
    cache_dir="/tmp/agno_cache",
    cache_ttl=3600
)
def get_top_hackernews_stories(num_stories: int = 5) -> str:
    """
    Fetch the top stories from Hacker News.

    Args:
        num_stories: Number of stories to fetch (default: 5)

    Returns:
        str: The top stories in text format
    """
    response = httpx.get("https://hacker-news.firebaseio.com/v0/topstories.json")
    story_ids = response.json()

    stories = []
    for story_id in story_ids[:num_stories]:
        story_response = httpx.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
        story = story_response.json()
        stories.append(f"{story.get('title')} - {story.get('url', 'No URL')}")

    return "\n".join(stories)

agent = Agent(tools=[get_top_hackernews_stories])
agent.print_response("Show me the top news from Hacker News")
```

---

## @tool Parameters Reference

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Override for the function name |
| `description` | `str` | Override for the function description |
| `stop_after_tool_call` | `bool` | If True, the agent will stop after the function call |
| `tool_hooks` | `list[Callable]` | List of hooks that wrap the function execution |
| `pre_hook` | `Callable` | Hook to run before the function is executed |
| `post_hook` | `Callable` | Hook to run after the function is executed |
| `requires_confirmation` | `bool` | If True, requires user confirmation before execution |
| `requires_user_input` | `bool` | If True, requires user input before execution |
| `user_input_fields` | `list[str]` | List of fields that require user input |
| `external_execution` | `bool` | If True, the tool will be executed outside of the agent's control |
| `cache_results` | `bool` | If True, enable caching of function results |
| `cache_dir` | `str` | Directory to store cache files |
| `cache_ttl` | `int` | Time-to-live for cached results in seconds (default: 3600) |

---

## Custom Toolkits

For advanced use cases, create custom Toolkits by inheriting from `agno.tools.Toolkit`.

### Toolkit Creation Flow

1. Create a class inheriting from `agno.tools.Toolkit`
2. Add your functions to the class
3. **Important:** Include all functions in the `tools` argument of the Toolkit constructor

### Example: Shell Tools Toolkit

```python
from typing import List
from agno.agent import Agent
from agno.tools import Toolkit
from agno.utils.log import logger

class ShellTools(Toolkit):
    def __init__(self, **kwargs):
        super().__init__(name="shell_tools", tools=[self.run_shell_command], **kwargs)

    def run_shell_command(self, args: List[str], tail: int = 100) -> str:
        """
        Runs a shell command and returns the output or error.

        Args:
            args (List[str]): The command to run as a list of strings.
            tail (int): The number of lines to return from the output.
        Returns:
            str: The output of the command.
        """
        import subprocess

        logger.info(f"Running shell command: {args}")
        try:
            result = subprocess.run(args, capture_output=True, text=True)
            logger.debug(f"Result: {result}")
            logger.debug(f"Return code: {result.returncode}")
            if result.returncode != 0:
                return f"Error: {result.stderr}"
            # Return only the last n lines of the output
            return "\n".join(result.stdout.split("\n")[-tail:])
        except Exception as e:
            logger.warning(f"Failed to run shell command: {e}")
            return f"Error: {e}"

agent = Agent(tools=[ShellTools()], markdown=True)
agent.print_response("List all the files in my home directory.")
```

---

## Summary

Agno's custom tools framework provides:
- Simple function-to-tool conversion
- Powerful `@tool` decorator with extensive configuration options
- Toolkit class for organizing related tools
- Built-in caching, hooks, and user interaction controls
- Flexible execution models (synchronous, external, with confirmation)

[Source](https://docs.agno.com/concepts/tools/custom-tools)