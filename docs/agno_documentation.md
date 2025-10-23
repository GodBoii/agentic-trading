Here's the documentation markdown from the URL:

---

# Introduction to Agno

Use it to build multi-agent systems with memory, knowledge, human in the loop and MCP support. You can orchestrate agents as multi-agent teams (more autonomy) or step-based agentic workflows (more control). Here's an example of an Agent that connects to an MCP server, manages conversation state in a database, and is served using a FastAPI application that you can interact with using the [AgentOS UI](https://os.agno.com/).

```python
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.anthropic import Claude
from agno.os import AgentOS
from agno.tools.mcp import MCPTools

# ************* Create Agent *************
agno_agent = Agent(
    name="Agno Agent",
    model=Claude(id="claude-sonnet-4-5"),
    # Add a database to the Agent
    db=SqliteDb(db_file="agno.db"),
    # Add the Agno MCP server to the Agent
    tools=[MCPTools(transport="streamable-http", url="https://docs.agno.com/mcp")],
    # Add the previous session history to the context
    add_history_to_context=True,
    markdown=True,
)


# ************* Create AgentOS *************
agent_os = AgentOS(agents=[agno_agent])
# Get the FastAPI app for the AgentOS
app = agent_os.get_app()

# ************* Run AgentOS *************
if __name__ == "__main__":
    agent_os.serve(app="agno_agent:app", reload=True)
```

## What is the AgentOS?

AgentOS is a high-performance runtime for multi-agent systems. Key features include:

1.  **Pre-built FastAPI runtime**: AgentOS ships with a ready-to-use FastAPI app for running your agents, teams, and workflows. This gives you a major head start in building your AI product.
2.  **Integrated UI**: The [AgentOS UI](https://os.agno.com/) connects directly to your runtime, letting you test, monitor, and manage your system in real time. This gives you unmatched visibility and control over your system.
3.  **Private by design**: AgentOS runs entirely in your cloud, ensuring complete data privacy. No data ever leaves your system. This is ideal for security-conscious enterprises.

Here's how the [AgentOS UI](https://os.agno.com/) looks like:

## The Complete Agentic Solution

For companies building agents, Agno provides the complete solution:

*   The fastest framework for building agents, multi-agent teams and agentic workflows.
*   A ready-to-use FastAPI app that gets you building AI products on day one.
*   A control plane for testing, monitoring and managing your system.

We bring a novel architecture that no other framework provides, your AgentOS runs securely in your cloud, and the control plane connects directly to it from your browser. You don't need to send data to any external services or pay retention costs, you get complete privacy and control.

## Getting started

If you're new to Agno, follow the [quickstart](https://docs.agno.com/introduction/quickstart) to build your first Agent and run it using the AgentOS. After that, checkout the [examples gallery](https://docs.agno.com/examples/introduction) and build real-world applications with Agno.

---

[Source](https://docs.agno.com/introduction)