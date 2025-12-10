# Documentation from Agno.com

## 1. Running Teams

[Source](https://docs.agno.com/basics/teams/running-teams)

---

Run your Team by calling `Team.run()` or `Team.arun()`. Below is a flowchart that explains how the team runs:

**Execution Flow Diagram**

![Team execution flow](https://sspark.genspark.ai/cfimages?u1=5z5q9S2IJpl3AOaAeCSmeO8NyDsFqjzDbm1%2BTyqcvR9g4YidxTHLxYQV5jZ6W%2FTyzMgRXyBSMarspTfMSIOOfhJu3mYI7bOBXqNgpe21MRrfdsqXt22SJ65PNwX5jgRz7iMmW9CoRfgOmZNQgDEjnVd6%2BS%2FZlOjFVErtKdrEvxLCSBvr7ltGRURTv3iQ00NKQuHLhNFmP%2BJI87%2BMP9Kf0vaXvjOBZkAJO0izkeuM1A%3D%3D&u2=nPxpaOwC2eEGxzph&width=1024)

### Execution Flow Steps:

1. **Pre-hooks execute** (if configured) to perform validation or setup before the run starts.
2. **Reasoning agent runs** (if enabled) to plan and break down the task.
3. **Context is built** including system message, user message, chat history, user memories, session state, and other inputs.
4. **Model is invoked** with the prepared context.
5. **Model decides** whether to respond directly, call provided tools, or delegate requests to team members.
6. **If delegation occurs**, member agents execute their tasks concurrently (in `async` mode) and return results to the team leader. The team-leader model processes these results and may delegate further or respond.
7. **Response is processed** and parsed into an [`output_schema`](https://docs.agno.com/basics/input-output/overview#structured-output) if provided.
8. **Post-hooks execute** (if configured) to perform final validation or transformation of the final output.
9. **Session and metrics are stored** in the database (if configured).
10. **TeamRunOutput is returned** to the caller with the final response.

### Basic Execution

The `Team.run()` function runs the team and returns the output either as a `TeamRunOutput` object or as a stream of `TeamRunOutputEvent` and `RunOutputEvent` (for member agents) objects (when `stream=True`). For example:

```python
from agno.team import Team
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.utils.pprint import pprint_run_response

news_agent = Agent(
    name="News Agent",
    model=OpenAIChat(id="gpt-4o"),
    role="Get the latest news",
    tools=[DuckDuckGoTools()]
)
weather_agent = Agent(
    name="Weather Agent",
    model=OpenAIChat(id="gpt-4o"),
    role="Get the weather for the next 7 days",
    tools=[DuckDuckGoTools()]
)

team = Team(
    name="News and Weather Team",
    members=[news_agent, weather_agent],
    model=OpenAIChat(id="gpt-4o")
)

# Run team and return the response as a variable
response = team.run(input="What is the weather in Tokyo?")
# Print the response in markdown format
pprint_run_response(response, markdown=True)
```

### Run Output

The `Team.run()` function returns a `TeamRunOutput` object when not streaming. This object contains the output content, the list of messages sent to the model, the metrics of the run, the model used for the run, and an optional list of member responses. See the detailed schema in the [TeamRunOutput](https://docs.agno.com/reference/teams/team-response) documentation.

### Streaming

To enable streaming, set `stream=True` when calling `run()`. This will return an iterator of `TeamRunOutputEvent` objects instead of a single `TeamRunOutput` object.

```python
from typing import Iterator
from agno.team import Team
from agno.agent import Agent
from agno.models.openai import OpenAIChat

news_agent = Agent(name="News Agent", role="Get the latest news")
weather_agent = Agent(name="Weather Agent", role="Get the weather for the next 7 days")

team = Team(
    name="News and Weather Team",
    members=[news_agent, weather_agent],
    model=OpenAIChat(id="gpt-4o")
)

# Run team and return the response as a stream
stream: Iterator[TeamRunOutputEvent] = team.run("What is the weather in Tokyo?", stream=True)
for chunk in stream:
    print(chunk.content, end="", flush=True)
```

#### Streaming team events

When you stream a response, only the `TeamRunContent` events will be streamed by default. You can also stream all run events by setting `stream_events=True`. This will provide real-time updates about the teams internal processes, like tool calling or reasoning:

```python
# Stream all events
response_stream = team.run(
    "What is the weather in Tokyo?",
    stream=True,
    stream_events=True
)
```

#### Streaming member events

When streaming events with `stream_events=True`, the team leader also streams the events from team members to the caller. When your team is running asynchronously (using `arun`), the members will run concurrently if the team leader delegates to multiple members in one request. This means you will receive member events concurrently and the order of the events is not guaranteed. You can disable this by setting `stream_member_events=False`.

```python
team = Team(
    name="News and Weather Team",
    members=[news_agent, weather_agent],
    model=OpenAIChat(id="gpt-4o"),
    stream_member_events=False
)

response_stream = team.run(
    "What is the weather in Tokyo?",
    stream=True,
    stream_events=True)
```

#### Handling Events

You can process events as they arrive by iterating over the response stream:

```python
from agno.team import Team
from agno.run.team import TeamRunEvent
from agno.run.agent import RunEvent
from agno.models.openai import OpenAIChat
from agno.agent import Agent
from agno.tools.duckduckgo import DuckDuckGoTools

weather_agent = Agent(name="Weather Agent", role="Get the weather for the next 7 days", tools=[DuckDuckGoTools()])
team = Team(
    name="Test Team",
    members=[weather_agent],
    model=OpenAIChat(id="gpt-4o-mini")
)

response_stream = team.run("What is the weather in Tokyo?", stream=True, stream_events=True)

for event in response_stream:
    if event.event == TeamRunEvent.run_content:
        print(event.content, end="", flush=True)
    elif event.event == TeamRunEvent.tool_call_started:
        print(f"Team tool call started")
    elif event.event == TeamRunEvent.tool_call_completed:
        print(f"Team tool call completed")
    elif event.event == RunEvent.tool_call_started:
        print(f"Member tool call started")
    elif event.event == RunEvent.tool_call_completed:
        print(f"Member tool call completed")
    elif event.event == TeamRunEvent.run_started:
        print(f"Run started")
    elif event.event == TeamRunEvent.run_completed:
        print(f"Run completed")
```

#### Storing Events

You can store all the events that happened during a run on the `TeamRunOutput` object.

```python
team = Team(
    name="Story Team",
    members=[],
    model=OpenAIChat(id="gpt-4o"),
    store_events=True
)
```

By default the `TeamRunContentEvent` and `RunContentEvent` events are not stored. You can modify which events are skipped by setting the `events_to_skip` parameter. For example:

```python
team = Team(
    name="Story Team",
    members=[],
    model=OpenAIChat(id="gpt-4o"),
    store_events=True,
    events_to_skip=[]  # Include all events
)
```

See the full [`TeamRunOutput` schema](https://docs.agno.com/reference/teams/team-response) for more details.

#### Event Types

The following events are streamed when `stream_events=True` by the `Team.run()` and `Team.arun()` functions depending on teams configuration:

**Core Events**

| Event Type | Description |
| --- | --- |
| `TeamRunStarted` | Indicates the start of a run |
| `TeamRunContent` | Contains the models response text as individual chunks |
| `TeamRunContentCompleted` | Signals completion of content streaming |
| `TeamRunIntermediateContent` | Contains the models intermediate response text as individual chunks. This is used when `output_model` is set. |
| `TeamRunCompleted` | Signals successful completion of the run |
| `TeamRunError` | Indicates an error occurred during the run |
| `TeamRunCancelled` | Signals that the run was cancelled |

**Tool Events**

| Event Type | Description |
| --- | --- |
| `TeamToolCallStarted` | Indicates the start of a tool call |
| `TeamToolCallCompleted` | Signals completion of a tool call, including tool call results |

**Reasoning Events**

| Event Type | Description |
| --- | --- |
| `TeamReasoningStarted` | Indicates the start of the teams reasoning process |
| `TeamReasoningStep` | Contains a single step in the reasoning process |
| `TeamReasoningCompleted` | Signals completion of the reasoning process |

**Memory Events**

| Event Type | Description |
| --- | --- |
| `TeamMemoryUpdateStarted` | Indicates that the team is updating its memory |
| `TeamMemoryUpdateCompleted` | Signals completion of a memory update |

**Session Summary Events**

| Event Type | Description |
| --- | --- |
| `TeamSessionSummaryStarted` | Indicates the start of session summary generation |
| `TeamSessionSummaryCompleted` | Signals completion of session summary generation |

**Pre-Hook Events**

| Event Type | Description |
| --- | --- |
| `TeamPreHookStarted` | Indicates the start of a pre-run hook |
| `TeamPreHookCompleted` | Signals completion of a pre-run hook execution |

**Post-Hook Events**

| Event Type | Description |
| --- | --- |
| `TeamPostHookStarted` | Indicates the start of a post-run hook |
| `TeamPostHookCompleted` | Signals completion of a post-run hook execution |

**Parser Model events**

| Event Type | Description |
| --- | --- |
| `TeamParserModelResponseStarted` | Indicates the start of the parser model response |
| `TeamParserModelResponseCompleted` | Signals completion of the parser model response |

**Output Model events**

| Event Type | Description |
| --- | --- |
| `TeamOutputModelResponseStarted` | Indicates the start of the output model response |
| `TeamOutputModelResponseCompleted` | Signals completion of the output model response |

See detailed documentation in the [TeamRunOutput](https://docs.agno.com/reference/teams/team-response) documentation.

#### Custom Events

If you are using your own custom tools, it will often be useful to be able to yield custom events. Your custom events will be yielded together with the rest of the expected Agno events. We recommend creating your custom event class extending the built-in `CustomEvent` class:

```python
from dataclasses import dataclass
from agno.run.team import CustomEvent

@dataclass
class CustomerProfileEvent(CustomEvent):
    """CustomEvent for customer profile."""

    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
```

You can then yield your custom event from your tool. The event will be handled internally as an Agno event, and you will be able to access it in the same way you would access any other Agno event.

```python
from agno.tools import tool

@tool()
async def get_customer_profile():
    """Example custom tool that simply yields a custom event."""

    yield CustomerProfileEvent(
        customer_name="John Doe",
        customer_email="[email protected]",
        customer_phone="1234567890",
    )
```

See the [full example](https://docs.agno.com/examples/basics/teams/events/custom_events) for more details.

### Specify Run User and Session

You can specify which user and session to use when running the team by passing the `user_id` and `session_id` parameters. This ensures the current run is associated with the correct user and session. For example:

```python
team.run("Get me my monthly report", user_id="[email protected]", session_id="session_123")
```

For more information see the [Sessions](https://docs.agno.com/basics/sessions/overview) documentation.

### Passing Images / Audio / Video / Files

You can pass images, audio, video, or files to the team by passing the `images`, `audio`, `video`, or `files` parameters. For example:

```python
team.run("Tell me a 5 second short story about this image", images=[Image(url="https://example.com/image.jpg")])
```

For more information see the [Multimodal](https://docs.agno.com/basics/multimodal) documentation.

### Passing Output Schema

You can pass an output schema for a specific run by passing the `output_schema` parameter. For example:

```python
from pydantic import BaseModel
from agno.agent import Agent
from agno.team import Team
from agno.models.openai import OpenAIChat

class DetailedReport(BaseModel):
    overview: str
    findings: list[str]

agent = Agent(name="Analyst", model=OpenAIChat(id="gpt-4o-mini"))
team = Team(members=[agent], model=OpenAIChat(id="gpt-4o-mini"))
team.run("Analyze the market", output_schema=DetailedReport)
```

For more information see the [Input & Output](https://docs.agno.com/basics/input-output/overview) documentation.

### Cancelling a Run

A run can be cancelled by calling the `Team.cancel_run()` method. See more details in the [Cancelling a Run](https://docs.agno.com/execution-control/run-cancellation/overview) documentation.

### Developer Resources

- View the [Team reference](https://docs.agno.com/reference/teams/team)
- View the [TeamRunOutput schema](https://docs.agno.com/reference/teams/team-response)
- View [Team Cookbook](https://github.com/agno-agi/agno/tree/main/cookbook/teams/README.md)

---

## 2. Team Delegation

[Source](https://docs.agno.com/basics/teams/delegation)

---

A `Team` internally has a team-leader agent that delegates tasks and requests to team members. When you call `run` or `arun` on a team, the team leader uses a model to determine which member to delegate the task to.

![Team delegation flow](https://sspark.genspark.ai/cfimages?u1=4XRC4%2FmmKCRVAddAqDIr8zQvOpH7X83paqyao6ykBEmMiqyQ9GOC%2FpHTydSPkZ5rtqHGlgWoOkckU96MdLKwHm%2BeWv3qEIrMThlRvSQe5YaBnYyZLHkkfM%2F6TnXqpDUKkPlN2vG%2Bv9cZTKHhE%2FCiv3%2BBsRWEYc5z4Jq5QLh2p2N9Q5kvQnNUtRUH00%2FyVACE54tEVir0h5wu3y%2BzOPDYrU35kqLjYWQNB1P%2Fr0JqLyc%3D&u2=7wNwcIzz0sgNMlPj&width=1024)

### The basic flow is:

1. The team receives user input
2. The team leader analyzes the input and decides how to break it down into subtasks
3. The team leader delegates specific tasks to appropriate team members
4. Team members complete their assigned tasks and return their results
5. The team leader then either delegates to more team members, or synthesizes all outputs into a final, cohesive response to return to the user

### Delegation Control Options

There are various ways to control how the team delegates tasks to members:

- **How do I return the response of members directly?** See [Members respond directly](#members-respond-directly)
- **How do I send my user input directly to the members without the team leader synthesizing it?** See [Send input directly to members](#send-input-directly-to-members)
- **How do I make sure the team leader delegates the task to all members at the same time?** See [Delegate tasks to all members](#delegate-tasks-to-all-members-simultaneously)

### Members respond directly

By default, the team leader processes responses from members and synthesizes them into a single cohesive response. Set `respond_directly=True` to return member responses directly without team leader synthesis.

![Team direct response flow](https://sspark.genspark.ai/cfimages?u1=FwiD4XJjYs%2F0mPoTU509xXkT%2FVZaXeHnubN%2Fbz%2B7HnGIrpzNxBcT%2BW5TMgASpyJbalSIV1Z17fZ4C2whfTrT%2F3XAgx2DcRJSLGA2iaRHiS4ryNi%2BebuE9gsIdkqv1ecERzGZA%2Fs%2BduFeifZAWQTCNgEGiIlNMf579XCVyljM1Gsbmj3r3KagKeQWl%2F4Cn8G%2FOG882xluM6W2ANvmo2783MXjOuWD3pIapjKrnyw4Xnh1fqjsPGhp&u2=2m9E0wzMmAyPv8zi&width=1024)

**Example:** Create a language router that directs questions to language-specific agents:

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.team.team import Team

english_agent = Agent(
    name="English Agent",
    role="You can only answer in English",
    model=OpenAIChat(id="gpt-5-mini"),
    instructions=[
        "You must only respond in English",
    ],
)

japanese_agent = Agent(
    name="Japanese Agent",
    role="You can only answer in Japanese",
    model=OpenAIChat(id="gpt-5-mini"),
    instructions=[
        "You must only respond in Japanese",
    ],
)

multi_language_team = Team(
    name="Multi Language Team",
    model=OpenAIChat("gpt-4.5-preview"),
    respond_directly=True,
    members=[
        english_agent,
        japanese_agent,
    ],
    markdown=True,
    instructions=[
        "You are a language router that directs questions to the appropriate language agent.",
        "If the user asks in a language whose agent is not a team member, respond in English with:",
        "'I can only answer in the following languages: English and Japanese. Please ask your question in one of these languages.'",
        "Always check the language of the user's input before routing to an agent.",
        "For unsupported languages like Italian, respond in English with the above message.",
    ],
    show_members_responses=True,
)

# Ask "How are you?" in all supported languages
multi_language_team.print_response("How are you?", stream=True)  # English
multi_language_team.print_response("元気ですか?", stream=True)  # Japanese
```

### Send input directly to members

By default, the team leader determines what task to give each member based on the user input. Set `determine_input_for_members=False` to send the original user input **directly** to member agents. The team leader still selects which members to delegate to, but doesn't transform the input.

![Send input directly to members flow](https://sspark.genspark.ai/cfimages?u1=bIduJl4gReGy1Ib1FS%2FgaHaZ5vThttfYRq2zH%2Fj3EgKSbYjTADiD8qBaX8SUi%2Bpn1Qa2P22jYuPKaw6qwXaCMIfrgkIxn3a8Pb%2F7gaMGKoR8BQ19FiOZ%2B96vLZjQqP4eXiMMYs7%2Bzctdip3d5FSCFACrnCvde6kG4ocRSrcVH5wtpCbJL2upkNcLxkQlo8659fmYMRTf%2BOs2E4nECcP3XfY%2FEAH0CoIUDEDZgCgZUtU0&u2=sFa7yMbN9mTG7tjf&width=1024)

**Example:** Send structured Pydantic input directly to a specialized research agent:

```python
from typing import List
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.team.team import Team
from agno.tools.hackernews import HackerNewsTools
from pydantic import BaseModel, Field


class ResearchTopic(BaseModel):
    """Structured research topic with specific requirements."""
    topic: str = Field(description="The main research topic")
    focus_areas: List[str] = Field(description="Specific areas to focus on")
    target_audience: str = Field(description="Who this research is for")
    sources_required: int = Field(description="Number of sources needed", default=5)


# Create specialized Hacker News research agent
hackernews_agent = Agent(
    name="Hackernews Agent",
    model=OpenAIChat(id="gpt-5-mini"),
    tools=[HackerNewsTools()],
    role="Extract key insights and content from Hackernews posts",
    instructions=[
        "Search Hacker News for relevant articles and discussions",
        "Extract key insights and summarize findings",
        "Focus on high-quality, well-discussed posts",
    ],
)

# Create collaborative research team
team = Team(
    name="Hackernews Research Team",
    model=OpenAIChat(id="gpt-5-mini"),
    members=[hackernews_agent],
    determine_input_for_members=False,  # The member gets the input directly
    instructions=[
        "Conduct thorough research based on the structured input",
        "Address all focus areas mentioned in the research topic",
        "Tailor the research to the specified target audience",
        "Provide the requested number of sources",
    ],
    show_members_responses=True,
)

# Use Pydantic model as structured input
research_request = ResearchTopic(
    topic="AI Agent Frameworks",
    focus_areas=["AI Agents", "Framework Design", "Developer Tools", "Open Source"],
    target_audience="Software Developers and AI Engineers",
    sources_required=7,
)

# Execute research with structured input
team.print_response(input=research_request)
```

### Passthrough Teams

It is a common pattern to have a team that decides which member to delegate the request to, and then passes the request to the team member without any modification, and also applies no processing to the response before returning it to the user. I.e. this team is a passthrough team (or router team). This means setting both `respond_directly=True` and `determine_input_for_members=False`.

![Passthrough team flow](https://sspark.genspark.ai/cfimages?u1=eP2RFM7%2BbgQjLUImpcAlievuIhEBkGEAHFZFIG0snOOnJ9JixMorICGwTVDhGMdIJcc1zX60wL%2FOr4Yb4U6%2FkXh3y6dYQ8XH%2FHrkYbfMtjxzohEgal8HedHAi7gRPctU5aDYhCRZ%2BuGDp2Tzk7VmaG20GMgK%2B1kvQiw%2BomuQzZwL3895orn8wAJk7saS%2FEEzf5gd0CJ8aPc1%2B99vxBcPicQUa3QsivAwMZgxmOPsGTishE8%3D&u2=KK8bugE%2BtQfpTpt1&width=1024)

**Example:**

```python
from agno.team.team import Team
from agno.agent import Agent
from agno.models.openai import OpenAIChat

team = Team(
    name="Question Router Team",
    model=OpenAIChat(id="gpt-5-mini"),
    members=[
        Agent(name="Big Question Agent", role="You handle BIG questions"),
        Agent(name="Small Question Agent", role="You handle SMALL questions"),
    ],
    respond_directly=True,  # Return member responses directly
    determine_input_for_members=False,  # Send input directly to members
)

team.print_response(input="What is the capital of France?", stream=True)
team.print_response(input="What is the meaning of life?", stream=True)
```

### Delegate tasks to all members simultaneously

Set `delegate_to_all_members=True` to delegate the task to **all members at once**, rather than selectively choosing members. When running asynchronously (using `arun`), all members execute **concurrently** for maximum parallelism.

![Delegate tasks to all members simultaneously flow](https://sspark.genspark.ai/cfimages?u1=slvRQWi1MCA2r9ac64PpGNSHq0za4IVhUymJSgM2dFFMBV6CMjsmF4AuJpw6Is6nepPbllZ0Co2rZC8FjyPlwS2Vs6qv6y1hyP0E08kcvQhYaaoom6Doeh32LJMQw9PwEYUhoXUrVGwN5kj1KqoC0GLOVSO%2FZ1pqOOEKO9zG9qIgdHOCEoQwIN%2BIDSlEUOD01XoZX63%2BTbFrFFGrbJN4mEELcrqi416TnYmA3oQugpgD6x1KcQAfNX0Bpqtf1sU%3D&u2=I9%2FPCg3YevgKlyXs&width=1024)

**Example:** Research team that gathers perspectives from multiple sources simultaneously:

```python
import asyncio
from textwrap import dedent
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.team.team import Team
from agno.tools.arxiv import ArxivTools
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.hackernews import HackerNewsTools

reddit_researcher = Agent(
    name="Reddit Researcher",
    role="Research a topic on Reddit",
    model=OpenAIChat(id="gpt-5-mini"),
    tools=[DuckDuckGoTools()],
    add_name_to_context=True,
    instructions=dedent("""
    You are a Reddit researcher.
    You will be given a topic to research on Reddit.
    You will need to find the most relevant posts on Reddit.
    """),
)

hackernews_researcher = Agent(
    name="HackerNews Researcher",
    model=OpenAIChat("gpt-5-mini"),
    role="Research a topic on HackerNews.",
    tools=[HackerNewsTools()],
    add_name_to_context=True,
    instructions=dedent("""
    You are a HackerNews researcher.
    You will be given a topic to research on HackerNews.
    You will need to find the most relevant posts on HackerNews.
    """),
)

academic_paper_researcher = Agent(
    name="Academic Paper Researcher",
    model=OpenAIChat("gpt-5-mini"),
    role="Research academic papers and scholarly content",
    tools=[DuckDuckGoTools(), ArxivTools()],
    add_name_to_context=True,
    instructions=dedent("""
    You are a academic paper researcher.
    You will be given a topic to research in academic literature.
    You will need to find relevant scholarly articles, papers, and academic discussions.
    Focus on peer-reviewed content and citations from reputable sources.
    Provide brief summaries of key findings and methodologies.
    """),
)

twitter_researcher = Agent(
    name="Twitter Researcher",
    model=OpenAIChat("gpt-5-mini"),
    role="Research trending discussions and real-time updates",
    tools=[DuckDuckGoTools()],
    add_name_to_context=True,
    instructions=dedent("""
    You are a Twitter/X researcher.
    You will be given a topic to research on Twitter/X.
    You will need to find trending discussions, influential voices, and real-time updates.
    Focus on verified accounts and credible sources when possible.
    Track relevant hashtags and ongoing conversations.
    """),
)

agent_team = Team(
    name="Discussion Team",
    model=OpenAIChat("gpt-5-mini"),
    members=[
        reddit_researcher,
        hackernews_researcher,
        academic_paper_researcher,
        twitter_researcher,
    ],
    instructions=[
        "You are a discussion master.",
        "You have to stop the discussion when you think the team has reached a consensus.",
    ],
    delegate_to_all_members=True,
    markdown=True,
    show_members_responses=True,
)

if __name__ == "__main__":
    asyncio.run(
        agent_team.aprint_response(
            input="Start the discussion on the topic: 'What is the best way to learn to code?'",
            stream=True,
        )
    )
```

### Developer Resources

- View the [Team reference](https://docs.agno.com/reference/teams/team)
- View [Cookbook](https://github.com/agno-agi/agno/tree/main/cookbook/teams/basic_flows/README.md)

---

I've provided the complete documentation from both URLs in markdown format as requested. The documentation covers:

1. **Running Teams** - How to execute teams, streaming responses, event handling, and various configuration options
2. **Team Delegation** - How teams delegate tasks to members, including direct responses, passthrough teams, and concurrent execution patterns