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
    team.run("What's up?", user_id="user2", session_id="session2")
    

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
        # Select the model used for session summary creation and updates. If not specified, the agent\'s model is used by default.
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

