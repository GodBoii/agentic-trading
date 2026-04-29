# Agno Teams Documentation

## Teams Introduction




# Teams - Agno

Search...

Ctrl K

A Team is a collection of Agents (or other sub-teams) that work together to accomplish tasks. Teams can either **“coordinate”**, **“collaborate”** or **“route”** to solve a task. A `Team` has a list of `members` that can be instances of either `Agent` or `Team`.

    from agno.team import Team
    from agno.agent import Agent
    
    team = Team(members=[
        Agent(name="Agent 1", role="You answer questions in English"),
        Agent(name="Agent 2", role="You answer questions in Chinese"),
        Team(name="Team 1", role="You answer questions in French"),
    ])
    

The team will transfer tasks to the members depending on the `mode` of the team. As with agents, teams support the following features:

*   **Model:** Set the model that is used by the “team leader” to delegate tasks to the team members.
*   **Instructions:** Instruct the team leader on how to solve problems. The names, descriptions and roles of team members are automatically provided to the team leader.
*   **Tools:** If the team leader needs to be able to use tools directly, you can add tools to the team.
*   **Reasoning:** Enables the team leader to “think” before responding or delegating tasks to team members, and “analyze” the results of team members’ responses.
*   **Knowledge:** If the team needs to search for information, you can add a knowledge base to the team. This is accessible to the team leader.
*   **Storage:** The Team’s session history and state is stored in a database. This enables your team to continue conversations from where they left off, enabling multi-turn, long-term conversations.
*   **Memory:** Gives Teams the ability to store and recall information from previous interactions, allowing them to learn user preferences and personalize their responses.

It is recommended to specify the `name` and the `role` fields of each team member, for better identification by the team leader.

## Guides

## Developer Resources

*   View [Usecases]()
*   View [Examples]()
*   View [Cookbook]()

Was this page helpful?

YesNo






## Running your Team

The `Team.run()` function runs the team and generates a response, either as a `TeamRunOutput` object or a stream of `TeamRunOutputEvent` objects.

Many of our examples use `team.print_response()` which is a helper utility to print the response in the terminal. It uses `team.run()` under the hood.

## Running your Team

Here’s how to run your team. The response is captured in the `response` and `response_stream` variables.

    from agno.team import Team
    from agno.models.openai import OpenAIChat
    
    agent_1 = Agent(name="News Agent", role="Get the latest news")
    
    agent_2 = Agent(name="Weather Agent", role="Get the weather for the next 7 days")
    
    team = Team(name="News and Weather Team", members=[agent_1, agent_2])
    
    # Synchronous execution
    result = team.run("What is the weather in Tokyo?")
    
    # Asynchronous execution
    result = await team.arun("What is the weather in Tokyo?")
    

You can also run the agent asynchronously using the `Team.arun()` method.

### Print Response

For development purposes, you can also print the response in the terminal using the `Team.print_response()` method.

    team.print_response("What is the weather in Tokyo?")
    
    # Or for streaming
    team.print_response("What is the weather in Tokyo?", stream=True)
    

The `Team.print_response()` method is a helper method that uses the `Team.run()` method under the hood. This is only for convenience during development and not recommended for production use.See the [Team class reference]() for more details.

### Typed inputs and outputs

Teams support the same typesafe input and output patterns as individual agents, allowing you to define structured data schemas for validation and consistent response formats. For comprehensive information about using Pydantic models for input validation and output schema definition, see the [Input and Output]() documentation. All patterns shown there apply to teams as well.

You can set the `input_schema` on the team to validate the input and `output_schema` to ensure structured outputs. See more details in the [Input and Output]() documentation.

### RunOutput

The `Team.run()` function returns a `TeamRunOutput` object when not streaming. Here are some of the core attributes:

*   `run_id`: The id of the run.
*   `team_id`: The id of the team.
*   `team_name`: The name of the team.
*   `session_id`: The id of the session.
*   `user_id`: The id of the user.
*   `content`: The response content.
*   `content_type`: The type of content. In the case of structured output, this will be the class name of the pydantic model.
*   `reasoning_content`: The reasoning content.
*   `messages`: The list of messages sent to the model.
*   `metrics`: The metrics of the run. For more details see [Metrics]().
*   `model`: The model used for the run.
*   `member_responses`: The list of member responses. Optional to add when `store_member_responses=True` on the `Team`.

See detailed documentation in the [TeamRunOutput]() documentation.

## Streaming Responses

To enable streaming, set `stream=True` when calling `run()`. This will return an iterator of `TeamRunOutputEvent` objects instead of a single response.

    from agno.team import Team
    from agno.models.openai import OpenAIChat
    
    agent_1 = Agent(name="News Agent", role="Get the latest news")
    
    agent_2 = Agent(name="Weather Agent", role="Get the weather for the next 7 days")
    
    team = Team(name="News and Weather Team", members=[agent_1, agent_2])
    
    # Synchronous execution
    for chunk in team.run("What is the weather in Tokyo?", stream=True, stream_intermediate_steps=True):
        print(chunk.content, end="", flush=True)
    
    # Asynchronous execution
    async for chunk in team.arun("What is the weather in Tokyo?", stream=True, stream_intermediate_steps=True):
        print(chunk.content, end="", flush=True)
    

Throughout the execution of a team, multiple events take place, and we provide these events in real-time for enhanced team transparency. You can enable streaming of intermediate steps by setting `stream_intermediate_steps=True`.

    # Stream with intermediate steps
    response_stream = team.run(
        "What is the weather in Tokyo?",
        stream=True,
        stream_intermediate_steps=True
    )
    

### Handling Events

You can process events as they arrive by iterating over the response stream:

    response_stream = team.run("Your prompt", stream=True, stream_intermediate_steps=True)
    
    for event in response_stream:
        if event.event == "TeamRunContent":
            print(f"Content: {event.content}")
        elif event.event == "TeamToolCallStarted":
            print(f"Tool call started: {event.tool}")
        elif event.event == "TeamReasoningStep":
            print(f"Reasoning step: {event.content}")
        ...
    

Team member events are yielded during team execution when a team member is being executed. You can disable this by setting `stream_member_events=False`.

### Storing Events

You can store all the events that happened during a run on the `RunOutput` object.

    from agno.team import Team
    from agno.models.openai import OpenAIChat
    from agno.utils.pprint import pprint_run_response
    
    team = Team(model=OpenAIChat(id="gpt-5-mini"), members=[], store_events=True)
    
    response = team.run("Tell me a 5 second short story about a lion", stream=True, stream_intermediate_steps=True)
    pprint_run_response(response)
    
    for event in response.events:
        print(event.event)
    

By default the `TeamRunContentEvent` and `RunContentEvent` events are not stored. You can modify which events are skipped by setting the `events_to_skip` parameter. For example:

    team = Team(model=OpenAIChat(id="gpt-5-mini"), members=[], store_events=True, events_to_skip=[TeamRunEvent.run_started.value])
    

### Event Types

The following events are sent by the `Team.run()` and `Team.arun()` functions depending on team’s configuration:

#### Core Events

| Event Type | Description |
| --- | --- |
| `TeamRunStarted` | Indicates the start of a run |
| `TeamRunContent` | Contains the model’s response text as individual chunks |
| `TeamRunCompleted` | Signals successful completion of the run |
| `TeamRunError` | Indicates an error occurred during the run |
| `TeamRunCancelled` | Signals that the run was cancelled |
| Event Type | Description |
| --- | --- |
| `TeamToolCallStarted` | Indicates the start of a tool call |
| `TeamToolCallCompleted` | Signals completion of a tool call, including tool call results |

#### Reasoning Events

| Event Type | Description |
| --- | --- |
| `TeamReasoningStarted` | Indicates the start of the team’s reasoning process |
| `TeamReasoningStep` | Contains a single step in the reasoning process |
| `TeamReasoningCompleted` | Signals completion of the reasoning process |

#### Memory Events

| Event Type | Description |
| --- | --- |
| `TeamMemoryUpdateStarted` | Indicates that the team is updating its memory |
| `TeamMemoryUpdateCompleted` | Signals completion of a memory update |

#### Parser Model events

| Event Type | Description |
| --- | --- |
| `TeamParserModelResponseStarted` | Indicates the start of the parser model response |
| `TeamParserModelResponseCompleted` | Signals completion of the parser model response |

#### Output Model events

| Event Type | Description |
| --- | --- |
| `TeamOutputModelResponseStarted` | Indicates the start of the output model response |
| `TeamOutputModelResponseCompleted` | Signals completion of the output model response |See detailed documentation in the [TeamRunOutput]() documentation.

### Custom Events

If you are using your own custom tools, it will often be useful to be able to yield custom events. Your custom events will be yielded together with the rest of the expected Agno events. We recommend creating your custom event class extending the built-in `CustomEvent` class:

    from dataclasses import dataclass
    from agno.run.team import CustomEvent
    
    @dataclass
    class CustomerProfileEvent(CustomEvent):
        """CustomEvent for customer profile."""
    
        customer_name: Optional[str] = None
        customer_email: Optional[str] = None
        customer_phone: Optional[str] = None
    

You can then yield your custom event from your tool. The event will be handled internally as an Agno event, and you will be able to access it in the same way you would access any other Agno event.

    from agno.tools import tool
    
    @tool()
    async def get_customer_profile():
        """Example custom tool that simply yields a custom event."""
    
        yield CustomerProfileEvent(
            customer_name="John Doe",
            customer_email="john.doe@example.com",
            customer_phone="1234567890",
        )
    

See the [full example]() for more details.

## Interactive CLI

You can also interact with the team via a CLI.

    team.cli_app(input="What is the weather in Tokyo?", stream=True)
    

See the [Team class reference]() for more details.

## Agno Telemetry

Agno logs which model an team used so we can prioritize updates to the most popular providers. You can disable this by setting `AGNO_TELEMETRY=false` in your environment or by setting `telemetry=False` on the team.

    export AGNO_TELEMETRY=false
    

or:

    team = Team(model=OpenAIChat(id="gpt-5-mini"), members=[], telemetry=False)
    

See the [Team class reference]() for more details.






## Team Sessions

# Team Sessions - Agno

Search...

Ctrl K

Learn about Team sessions.

When we call `Team.run()`, it creates a stateless, singular Team run.

But what if we want to continue this conversation i.e. have a multi-turn conversation? That’s where “Sessions” come in. In a session is collection of consecutive runs.

In practice, a session in the context of a Team is a multi-turn conversation between a user and the Team. Using a `session_id`, we can connect the conversation history and state across multiple runs.

See more details in the [Agent Sessions]() documentation.

## Multi-user, multi-session Teams

Each user that is interacting with a Team gets a unique set of sessions and you can have multiple users interacting with the same Team at the same time.

Set a `user_id` to connect a user to their sessions with the Team.

In the example below, we set a `session_id` to demo how to have multi-turn conversations with multiple users at the same time.

1.  Multi-user, multi-session example

    from agno.team import Team
    from agno.models.openai import OpenAIChat
    
    team = Team(model=OpenAIChat(id="gpt-5-mini"), members=[])
    
    # User 1
    team.run("Hello", user_id="user1", session_id="session1")
    team.run("How are you?", user_id="user1", session_id="session1")
    
    # User 2
    team.run("Hi", user_id="user2", session_id="session2")
    team.run("What\'s up?", user_id="user2", session_id="session2")
    

## Session Management

Agno provides a comprehensive API for managing sessions. You can retrieve, update, and delete sessions programmatically. This is particularly useful for building custom user interfaces or integrating with existing systems.

### Retrieving Sessions

You can retrieve a specific session by its ID or list all sessions associated with a team.

    # Retrieve a session by ID
    session = team.get_session("session1")
    
    # List all sessions for a team
    all_sessions = team.get_all_sessions()
    

### Updating Sessions

You can update session metadata, such as its name, description, or tags.

    session.update(name="New Session Name", description="Updated description")
    

### Deleting Sessions

You can delete a session by its ID.

    team.delete_session("session1")
    

## Session Summaries

"See more details in the [Agent Sessions]() documentation."

"The Team can store a condensed representations of the session, useful when chat histories gets too long. This is called a “Session Summary” in Agno. To enable session summaries, set `enable_session_summaries=True` on the `Team`."

"### Customize Session Summaries

You can adjust the session summaries by providing a custom `session_summary_prompt` to the `Team`. The `SessionSummaryManager` class is responsible for handling the model used to create and update session summaries. You can adjust it to personalize how summaries are created and updated:

    from agno.team import Team
    from agno.session import SessionSummaryManager
    from agno.models.openai import OpenAIChat
    from agno.db.sqlite import SqliteDb
    
    # Setup your database
    db = SqliteDb(db_file="agno.db")
    
    # Setup your Session Summary Manager, to adjust how summaries are created
    session_summary_manager = SessionSummaryManager(
        # Select the model used for session summary creation and updates. If not specified, the agent\\\'s model is used by default.
        model=OpenAIChat(id="gpt-5-mini"),
        # You can also overwrite the prompt used for session summary creation
        session_summary_prompt="Create a very succinct summary of the following conversation:",
    )
    
    # Now provide the adjusted Memory Manager to your Agent
    team = Team(
      members=[],
      db=db,
      session_summary_manager=session_summary_manager,
      enable_session_summaries=True,
    )
"

"Teams with storage enabled automatically have access to the message and run history of the session. You can access these messages using:

*   `agent.get_messages_for_session()` -> Gets access to all the messages for the session, for the current agent.
*   `agent.get_chat_history()` -> Gets access to all the unique messages for the session.

We can give the Agent access to the chat history in the following ways:

*   We can set `add_history_to_context=True` and `num_history_runs=5` to add the messages from the last 5 runs automatically to every message sent to the agent.
*   We can set `read_chat_history=True` to provide a `get_chat_history()` tool to your agent allowing it to read any message in the entire chat history.
*   **We recommend setting all 3: `add_history_to_context=True`, `num_history_runs=3` and `read_chat_history=True` for the best experience.**
*   We can also set `read_tool_call_history=True` to provide a `get_tool_call_history()` tool to your agent allowing it to read tool calls in reverse chronological order."



