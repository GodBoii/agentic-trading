Now let me compile all the documentation I've gathered. Here's the comprehensive documentation from the Agno agents overview and related pages:

---

# **Agno Agents Documentation**

## **Agents Overview**

**Agents are AI programs where a language model controls the flow of execution.** The core of an Agent is a model using tools in a loop, guided by instructions:

*   **Model:** controls the flow of execution. It decides whether to reason, act or respond.
*   **Instructions:** program the Agent, teaching it how to use tools and respond.
*   **Tools:** enable an Agent to take actions and interact with external systems.

Agents also have memory, knowledge, storage and the ability to reason:

*   **Memory:** gives Agents the ability to store and recall information from previous interactions, allowing them to learn and improve their responses.
*   **Storage:** is used by Agents to save session history and state in a database. Model APIs are stateless and storage makes Agents stateful, enabling multi-turn conversations.
*   **Knowledge:** is domain-specific information the Agent can **search at runtime** to provide better responses (RAG). Knowledge is stored in a vector database and this search at runtime pattern is known as **Agentic RAG** or **Agentic Search**.
*   **Reasoning:** enables Agents to think before responding and analyze the results of their actions before responding, this improves reliability and quality of responses.

### **Developer Resources**

*   View the [Agent schema](https://docs.agno.com/reference/agents/agent)
*   View [Cookbook](https://github.com/agno-agi/agno/tree/main/cookbook/agents/README.md)

---

## **Tools**

**Agents use tools to take actions and interact with external systems**. Tools are functions that an Agent can run to achieve tasks. For example: searching the web, running SQL, sending an email or calling APIs. You can use any python function as a tool or use a pre-built Agno **toolkit**. The general syntax is:

```python
from agno.agent import Agent

agent = Agent(
    # Add functions or Toolkits
    tools=[...],
)
```

Agno provides many pre-built **toolkits** that you can add to your Agents. For example, lets use the DuckDuckGo toolkit to search the web.

For more control, write your own python functions and add them as tools to an Agent. For example, here's how to add a `get_top_hackernews_stories` tool to an Agent.

```python
import json
import httpx

from agno.agent import Agent

def get_top_hackernews_stories(num_stories: int = 10) -> str:
    """Use this function to get top stories from Hacker News.

    Args:
        num_stories (int): Number of stories to return. Defaults to 10.
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

Read more about:

*   [Available toolkits](https://docs.agno.com/concepts/tools/toolkits)
*   [Creating your own tools](https://docs.agno.com/concepts/tools/custom-tools)

### **Accessing built-in parameters in tools**

You can access agent attributes like `session_state`, `dependencies`, `agent` and `team` in your tools. For example:

```python
from agno.agent import Agent

def get_shopping_list(session_state: dict) -> str:
    """Get the shopping list."""
    return session_state["shopping_list"]

agent = Agent(tools=[get_shopping_list], session_state={"shopping_list": ["milk", "bread", "eggs"]}, markdown=True)
agent.print_response("What's on my shopping list?", stream=True)
```

See more in the [Tool Built-in Parameters](https://docs.agno.com/concepts/tools/overview#tool-built-in-parameters) section.

### **Model Context Protocol (MCP) Support**

Agno supports [Model Context Protocol (MCP)](https://docs.agno.com/concepts/tools/mcp) tools. The general syntax is:

```python
from agno.agent import Agent
from agno.tools.mcp import MCPTools

async def run_mcp_agent():

    # Initialize the MCP tools
    mcp_tools = MCPTools(command=f"uvx mcp-server-git")

    # Connect to the MCP server
    await mcp_tools.connect()

    agent = Agent(tools=[mcp_tools], markdown=True)
    await agent.aprint_response("What is the license for this project?", stream=True)
    ...
```

---

## **Memory**

Memory is a part of the Agent's context that helps it provide the best, most personalized response.

### **User Memories**

Here's a simple example of using Memory in an Agent.

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.db.postgres import PostgresDb
from rich.pretty import pprint

user_id = "ava"

db_url = "postgresql+psycopg://ai:ai@localhost:5532/ai"

db = PostgresDb(
  db_url=db_url,
  memory_table="user_memories",  # Optionally specify a table name for the memories
)


# Initialize Agent
memory_agent = Agent(
    model=OpenAIChat(id="gpt-4.1"),
    db=db,
    # Give the Agent the ability to update memories
    enable_agentic_memory=True,
    # OR - Run the MemoryManager automatically after each response
    enable_user_memories=True,
    markdown=True,
)

db.clear_memories()

memory_agent.print_response(
    "My name is Ava and I like to ski.",
    user_id=user_id,
    stream=True,
    stream_intermediate_steps=True,
)
print("Memories about Ava:")
pprint(memory_agent.get_user_memories(user_id=user_id))

memory_agent.print_response(
    "I live in san francisco, where should i move within a 4 hour drive?",
    user_id=user_id,
    stream=True,
    stream_intermediate_steps=True,
)
print("Memories about Ava:")
pprint(memory_agent.get_user_memories(user_id=user_id))
```

### **Developer Resources**

*   View the [Agent schema](https://docs.agno.com/reference/agents/agent)
*   View [Examples](https://docs.agno.com/examples/concepts/memory)
*   View [Cookbook](https://github.com/agno-agi/agno/tree/main/cookbook/memory/)

---

## **Storage**

**Why do we need Session Storage?** Agents are ephemeral and stateless. When you run an Agent, no state is persisted automatically. In production environments, we serve (or trigger) Agents via an API and need to continue the same session across multiple requests. Storage persists the session history and state in a database and allows us to pick up where we left off. Storage also lets us inspect and evaluate Agent sessions, extract few-shot examples and build internal monitoring tools. It lets us **look at the data** which helps us build better Agents. Adding storage to an Agent, Team or Workflow is as simple as providing a `DB` driver and Agno handles the rest. You can use Sqlite, Postgres, Mongo or any other database you want. Here's a simple example that demonstrates persistence across execution cycles:

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.db.sqlite import SqliteDb
from rich.pretty import pprint

agent = Agent(
     model=OpenAIChat(id="gpt-5-mini"),
    # Fix the session id to continue the same session across execution cycles
    session_id="fixed_id_for_demo",
    db=SqliteDb(db_file="tmp/data.db"),
    # Make the agent aware of the session history
    add_history_to_context=True,
    num_history_runs=3,
)
agent.print_response("What was my last question?")
agent.print_response("What is the capital of France?")
agent.print_response("What was my last question?")
pprint(agent.get_messages_for_session())
```

The first time you run this, the answer to What was my last question? will not be available. But run it again and the Agent will able to answer properly. Because we have fixed the session id, the Agent will continue from the same session every time you run the script.

### **Benefits of Storage**

Storage has typically been an under-discussed part of Agent Engineering but we see it as the unsung hero of production agentic applications. In production, you need storage to:

*   Continue sessions: retrieve session history and pick up where you left off.
*   Get list of sessions: To continue a previous session, you need to maintain a list of sessions available for that agent.
*   Save session state between runs: save the Agent's state to a database or file so you can inspect it later.

But there is so much more:

*   Storage saves our Agent's session data for inspection and evaluations, including session metrics.
*   Storage helps us extract few-shot examples, which can be used to improve the Agent.
*   Storage enables us to build internal monitoring tools and dashboards.

### **Session table schema**

If you have a `db` configured for your agent, the sessions will be stored in a sessions table in your database. The schema for the sessions table is as follows:

| Field | Type | Description |
| --- | --- | --- |
| `session_id` | `str` | The unique identifier for the session. |
| `session_type` | `str` | The type of the session. |
| `agent_id` | `str` | The agent ID of the session. |
| `team_id` | `str` | The team ID of the session. |
| `workflow_id` | `str` | The workflow ID of the session. |
| `user_id` | `str` | The user ID of the session. |
| `session_data` | `dict` | The data of the session. |
| `agent_data` | `dict` | The data of the agent. |
| `team_data` | `dict` | The data of the team. |
| `workflow_data` | `dict` | The data of the workflow. |
| `metadata` | `dict` | The metadata of the session. |
| `runs` | `list` | The runs of the session. |
| `summary` | `dict` | The summary of the session. |
| `created_at` | `int` | The timestamp when the session was created. |
| `updated_at` | `int` | The timestamp when the session was last updated. |

This data is best displayed on the [sessions page of the AgentOS UI](https://os.agno.com/sessions).

### **Developer Resources**

*   View the [Agent schema](https://docs.agno.com/reference/agents/agent)
*   View [Examples](https://docs.agno.com/examples/concepts/db)
*   View [Cookbook](https://github.com/agno-agi/agno/tree/main/cookbook/db/)

---

## **Knowledge**

**Knowledge** stores domain-specific content that can be added to the context of the agent to enable better decision making.

The Agent can **search** this knowledge at runtime to make better decisions and provide more accurate responses. This **searching on demand** pattern is called Agentic RAG.

### **Knowledge for Agents**

Agno Agents use **Agentic RAG** by default, meaning when we provide `knowledge` to an Agent, it will search this knowledge base, at runtime, for the specific information it needs to achieve its task. For example:

```python
import asyncio

from agno.agent import Agent
from agno.db.postgres.postgres import PostgresDb
from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.knowledge.knowledge import Knowledge
from agno.vectordb.pgvector import PgVector

db = PostgresDb(
    db_url="postgresql+psycopg://ai:ai@localhost:5532/ai",
    knowledge_table="knowledge_contents",
)

# Create Knowledge Instance
knowledge = Knowledge(
    name="Basic SDK Knowledge Base",
    description="Agno 2.0 Knowledge Implementation",
    contents_db=db,
    vector_db=PgVector(
        table_name="vectors",
        db_url="postgresql+psycopg://ai:ai@localhost:5532/ai",
        embedder=OpenAIEmbedder(),
    ),
)
# Add from URL to the knowledge base
asyncio.run(
    knowledge.add_content_async(
        name="Recipes",
        url="https://agno-public.s3.amazonaws.com/recipes/ThaiRecipes.pdf",
        metadata={"user_tag": "Recipes from website"},
    )
)

agent = Agent(
    name="My Agent",
    description="Agno 2.0 Agent Implementation",
    knowledge=knowledge,
    search_knowledge=True,
)

agent.print_response(
    "How do I make chicken and galangal in coconut milk soup?",
    markdown=True,
)
```

We can give our agent access to the knowledge base in the following ways:

*   We can set `search_knowledge=True` to add a `search_knowledge_base()` tool to the Agent. `search_knowledge` is `True` **by default** if you add `knowledge` to an Agent.
*   We can set `add_knowledge_to_context=True` to automatically add references from the knowledge base to the Agent's context, based in your user message. This is the traditional RAG approach.

### **Custom knowledge retrieval**

If you need complete control over the knowledge base search, you can pass your own `knowledge_retriever` function with the following signature:

```python
def knowledge_retriever(agent: Agent, query: str, num_documents: Optional[int], **kwargs) -> Optional[list[dict]]:
  ...
```

Example of how to configure an agent with a custom retriever:

```python
def knowledge_retriever(agent: Agent, query: str, num_documents: Optional[int], **kwargs) -> Optional[list[dict]]:
  ...

agent = Agent(
    knowledge_retriever=knowledge_retriever,
    search_knowledge=True,
)
```

This function is called during `search_knowledge_base()` and is used by the Agent to retrieve references from the knowledge base.

### **Knowledge storage**

Knowledge content is tracked in a Contents DB and vectorized and stored in a Vector DB.

#### **Contents database**

The Contents DB is a database that stores the name, description, metadata and other information for any content you add to the knowledge base. Below is the schema for the Contents DB:

| Field | Type | Description |
| --- | --- | --- |
| `id` | `str` | The unique identifier for the knowledge content. |
| `name` | `str` | The name of the knowledge content. |
| `description` | `str` | The description of the knowledge content. |
| `metadata` | `dict` | The metadata for the knowledge content. |
| `type` | `str` | The type of the knowledge content. |
| `size` | `int` | The size of the knowledge content. Applicable only to files. |
| `linked_to` | `str` | The ID of the knowledge content that this content is linked to. |
| `access_count` | `int` | The number of times this content has been accessed. |
| `status` | `str` | The status of the knowledge content. |
| `status_message` | `str` | The message associated with the status of the knowledge content. |
| `created_at` | `int` | The timestamp when the knowledge content was created. |
| `updated_at` | `int` | The timestamp when the knowledge content was last updated. |
| `external_id` | `str` | The external ID of the knowledge content. Used when external vector stores are used, like LightRAG. |

This data is best displayed on the [knowledge page of the AgentOS UI](https://os.agno.com/knowledge).

#### **Vector databases**

Vector databases offer the best solution for retrieving relevant results from dense information quickly.

#### **Adding contents**

The typical way content is processed when being added to the knowledge base is:

For example, to add a PDF to the knowledge base:

```python
...
knowledge = Knowledge(
    name="Basic SDK Knowledge Base",
    description="Agno 2.0 Knowledge Implementation",
    vector_db=vector_db,
    contents_db=contents_db,
)

asyncio.run(
    knowledge.add_content_async(
        name="CV",
        path="cookbook/knowledge/testing_resources/cv_1.pdf",
        metadata={"user_tag": "Engineering Candidates"},
    )
)
```

### **Developer Resources**

*   View the [Agent schema](https://docs.agno.com/reference/agents/agent)
*   View the [Knowledge schema](https://docs.agno.com/reference/knowledge/knowledge)
*   View [Cookbook](https://github.com/agno-agi/agno/tree/main/cookbook/knowledge/)

---

## **Context Engineering**

Context engineering is the process of designing and controlling the information (context) that is sent to language models to guide their behavior and outputs. In practice, building context comes down to one question: "Which information is most likely to achieve the desired outcome?" In Agno, this means carefully crafting the system message, which includes the agent's description, instructions, and other relevant settings. By thoughtfully constructing this context, you can:

 * Steer the agent toward specific behaviors or roles.
 * Constrain or expand the agent's capabilities.
 * Ensure outputs are consistent, relevant, and aligned with your application's needs.
 * Enable advanced use cases such as multi-step reasoning, tool use, or structured output.

Effective context engineering is an iterative process: refining the system message, trying out different descriptions and instructions, and using features such as schemas, delegation, and tool integrations. The context of an Agno agent consists of the following:

 * System message: The system message is the main context that is sent to the agent, including all additional context
 * User message: The user message is the message that is sent to the agent.
 * Chat history: The chat history is the history of the conversation between the agent and the user.
 * Additional input: Any few-shot examples or other additional input that is added to the context.

### **System message context**

The following are some key parameters that are used to create the system message:

 1. Description: A description that guides the overall behaviour of the agent.
 2. Instructions: A list of precise, task-specific instructions on how to achieve its goal.
 3. Expected Output: A description of the expected output from the Agent.

The system message is built from the agent's description, instructions, and other settings.

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat

agent = Agent(
    model=OpenAIChat(id="gpt-5-mini"),
    description="You are a famous short story writer asked to write for a magazine",
    instructions=["Always write 2 sentence stories."],
    markdown=True,
    debug_mode=True,  # Set to True to view the detailed logs and see the compiled system message
)
agent.print_response("Tell me a horror story.", stream=True)
```

Will produce the following system message:

```
You are a famous short story writer asked to write for a magazine                                                                          
<instructions>                                                                                                                             
- Always write 2 sentence stories.                                                                                                         
</instructions>                                                                                                                            

<additional_information>                                                                                                                   
- Use markdown to format your answer
</additional_information>
```

### **System message Parameters**

The Agent creates a default system message that can be customized using the following agent parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| description | str | None | A description of the Agent that is added to the start of the system message. |
| instructions | List[str] | None | List of instructions added to the system prompt in `<instructions>` tags. Default instructions are also created depending on values for markdown, expected_output etc. |
| additional_context | str | None | Additional context added to the end of the system message. |
| expected_output | str | None | Provide the expected output from the Agent. This is added to the end of the system message. |
| markdown | bool | False | Add an instruction to format the output using markdown. |
| add_datetime_to_context | bool | False | If True, add the current datetime to the prompt to give the agent a sense of time. This allows for relative times like "tomorrow" to be used in the prompt |
| add_name_to_context | bool | False | If True, add the name of the agent to the context. |
| add_location_to_context | bool | False | If True, add the location of the agent to the context. This allows for location-aware responses and local context. |
| add_session_summary_to_context | bool | False | If True, add the session summary to the context. See sessions for more information. |
| add_memories_to_context | bool | False | If True, add the user memories to the context. See memory for more information. |
| add_session_state_to_context | bool | False | If True, add the session state to the context. See state for more information. |
| enable_agentic_knowledge_filters | bool | False | If True, let the agent choose the knowledge filters. See knowledge for more information. |
| system_message | str | None | Override the default system message. |
| build_context | bool | True | Optionally disable the building of the context. |

See the full Agent reference for more information.

### **Additional Context**

You can add additional context to the end of the system message using the additional_context parameter. Here, additional_context adds a note to the system message indicating that the agent can access specific database tables.

```python
from textwrap import dedent

from agno.agent import Agent
from agno.models.langdb import LangDB
from agno.tools.duckdb import DuckDbTools

duckdb_tools = DuckDbTools(
    create_tables=False, export_tables=False, summarize_tables=False
)
duckdb_tools.create_table_from_path(
    path="https://phidata-public.s3.amazonaws.com/demo_data/IMDB-Movie-Data.csv",
    table="movies",
)

agent = Agent(
    model=LangDB(id="llama3-1-70b-instruct-v1.0"),
    tools=[duckdb_tools],
    markdown=True,
    additional_context=dedent("""\
    You have access to the following tables:
    - movies: contains information about movies from IMDB.
    """),
)
agent.print_response("What is the average rating of movies?", stream=True)
```

### **Tool Instructions**

If you are using a Toolkit on your agent, you can add tool instructions to the system message using the instructions parameter:

```python
from agno.agent import Agent
from agno.tools.slack import SlackTools

slack_tools = SlackTools(
    instructions=["Use `send_message` to send a message to the user. If the user specifies a thread, use `send_message_thread` to send a message to the thread."],
    add_instructions=True,
)
agent = Agent(
    tools=[slack_tools],
)
```

These instructions are injected into the system message after the `<additional_information>` tags.

### **Few-shot learning with additional input**

You can add entire additional messages to your agent's context using the additional_input parameter. These messages are added to the context as if they were part of the conversation history. You can give your agent examples of how it should respond (also called "few-shot prompting").

### **Context Caching**

Most model providers support caching of system and user messages, though the implementation differs between providers. The general approach is to cache repetitive content and common instructions, and then reuse that cached content in subsequent requests as the prefix of your system message. In other words, if the model supports it, you can reduce the number of tokens sent to the model by putting static content at the start of your system message. Agno's context construction is designed to place the most likely static content at the beginning of the system message.

If you wish to fine-tune this, the recommended approach is to manually set the system message. Some examples of prompt caching:

 * OpenAI's prompt caching
 * Anthropic prompt caching -> See an Agno example of this
 * OpenRouter prompt caching

### **Developer Resources**

 * View the Agent schema
 * View Cookbook

---

## **Multimodal Agents**

Agno agents support text, image, audio, video and files inputs and can generate text, image, audio, video and files as output. For a complete overview of multimodal support, please checkout the [multimodal](https://docs.agno.com/concepts/multimodal/overview) documentation.

### **Multimodal inputs to an agent**

Let's create an agent that can understand images and make tool calls as needed

#### **Image Agent**

```python
from agno.agent import Agent
from agno.media import Image
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGoTools

agent = Agent(
    model=OpenAIChat(id="gpt-5-mini"),
    tools=[DuckDuckGoTools()],
    markdown=True,
)

agent.print_response(
    "Tell me about this image and give me the latest news about it.",
    images=[
        Image(
            url="https://upload.wikimedia.org/wikipedia/commons/0/0c/GoldenGateBridge-001.jpg"
        )
    ],
    stream=True,
)
```

See [Image as input](https://docs.agno.com/concepts/multimodal/images/image_input) for more details.

#### **Audio Agent**

```python
import base64

import requests
from agno.agent import Agent
from agno.media import Audio
from agno.models.openai import OpenAIChat

# Fetch the audio file and convert it to a base64 encoded string
url = "https://openaiassets.blob.core.windows.net/$web/API/docs/audio/alloy.wav"
response = requests.get(url)
response.raise_for_status()
wav_data = response.content

agent = Agent(
    model=OpenAIChat(id="gpt-5-mini-audio-preview", modalities=["text"]),
    markdown=True,
)
agent.print_response(
    "What is in this audio?", audio=[Audio(content=wav_data, format="wav")]
)
```

#### **Video Agent**

```python
from pathlib import Path

from agno.agent import Agent
from agno.media import Video
from agno.models.google import Gemini

agent = Agent(
    model=Gemini(id="gemini-2.0-flash-exp"),
    markdown=True,
)

# Please download "GreatRedSpot.mp4" using
# wget https://storage.googleapis.com/generativeai-downloads/images/GreatRedSpot.mp4
video_path = Path(__file__).parent.joinpath("GreatRedSpot.mp4")

agent.print_response("Tell me about this video", videos=[Video(filepath=video_path)])
```

### **Multimodal outputs from an agent**

Similar to providing multimodal inputs, you can also get multimodal outputs from an agent.

#### **Image Generation**

The following example demonstrates how to generate an image using DALL-E with an agent.

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.dalle import DalleTools

image_agent = Agent(
    model=OpenAIChat(id="gpt-5-mini"),
    tools=[DalleTools()],
    description="You are an AI agent that can generate images using DALL-E.",
    instructions="When the user asks you to create an image, use the `create_image` tool to create the image.",
    markdown=True,
)

image_agent.print_response("Generate an image of a white siamese cat")

images = image_agent.get_images()
if images and isinstance(images, list):
    for image_response in images:
        image_url = image_response.url
        print(image_url)
```

#### **Audio Response**

The following example demonstrates how to obtain both text and audio responses from an agent. The agent will respond with text and audio bytes that can be saved to a file.

```python
from agno.agent import Agent, RunOutput
from agno.models.openai import OpenAIChat
from agno.utils.audio import write_audio_to_file

agent = Agent(
    model=OpenAIChat(
        id="gpt-5-mini-audio-preview",
        modalities=["text", "audio"],
        audio={"voice": "alloy", "format": "wav"},
    ),
    markdown=True,
)
response: RunOutput = agent.run("Tell me a 5 second scary story")

# Save the response audio to a file
if response.response_audio is not None:
    write_audio_to_file(
        audio=agent.run_response.response_audio.content, filename="tmp/scary_story.wav"
    )
```

### **Multimodal inputs and outputs together**

You can create Agents that can take multimodal inputs and return multimodal outputs. The following example demonstrates how to provide a combination of audio and text inputs to an agent and obtain both text and audio outputs.

#### **Audio input and Audio output**

```python
import base64

import requests
from agno.agent import Agent
from agno.media import Audio
from agno.models.openai import OpenAIChat
from agno.utils.audio import write_audio_to_file

# Fetch the audio file and convert it to a base64 encoded string
url = "https://openaiassets.blob.core.windows.net/$web/API/docs/audio/alloy.wav"
response = requests.get(url)
response.raise_for_status()
wav_data = response.content

agent = Agent(
    model=OpenAIChat(
        id="gpt-5-mini-audio-preview",
        modalities=["text", "audio"],
        audio={"voice": "alloy", "format": "wav"},
    ),
    markdown=True,
)

agent.run("What's in these recording?", audio=[Audio(content=wav_data, format="wav")])

if agent.run_response.response_audio is not None:
    write_audio_to_file(
        audio=agent.run_response.response_audio.content, filename="tmp/result.wav"
    )
```

---

[Source](https://docs.agno.com/concepts/agents/overview)