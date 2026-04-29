# Agno Teams Documentation




## Storage




# Storage - Agno

Search...

Ctrl K

**Why do we need Session Storage?** Teams are ephemeral and stateless. When you run a Team, no state is persisted automatically. In production environments, we serve (or trigger) Teams via an API and need to continue the same session across multiple requests. Storage persists the session history and state in a database and allows us to pick up where we left off. Here is a simple example showing how to configure storage for a Team:

    from agno.team import Team
    from agno.db.postgres import PostgresDb
    
    db_url = "postgresql+psycopg://ai:ai@localhost:5532/ai"
    db = PostgresDb(db_url=db_url)
    
    team = Team(members=[], db=db)
    team.print_response("What is the capital of France?")
    team.print_response("What was my question?")
    
    

See [Agent Session Storage]() for more details on how sessions are stored in general.If you have a `db` configured for your team, the sessions will be stored in the sessions table in your database. The schema for the sessions table is as follows:
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
| `updated_at` | `int` | The timestamp when the session was last updated. |This data is best displayed on the [sessions page of the AgentOS UI]().

## Developer Resources

*   View the [Team schema]()
*   View [Cookbook]()

Was this page helpful?

YesNo






## Memory

# Teams with Memory

Search...

Ctrl K

The team can also manage user memories, just like agents:

    from agno.team import Team
    from agno.db.sqlite import SqliteDb
    
    db = SqliteDb(db_file="agno.db")
    
    team_with_memory = Team(
        name="Team with Memory",
        members=[agent1, agent2],
        db=db,
        enable_user_memories=True,
    )
    
    team_with_memory.print_response("Hi! My name is John Doe.")
    team_with_memory.print_response("What is my name?")
    

See more in the [Memory]() section.

Was this page helpful?

YesNo






## Metrics

# Metrics - Agno

Search...

Ctrl K

When you run a team in Agno, the response you get (**TeamRunOutput**) includes detailed metrics about the run. These metrics help you understand resource usage (like **token usage** and **time**), performance, and other aspects of the model and tool calls across both the team leader and team members. Metrics are available at multiple levels:

*   **Per-message**: Each message (assistant, tool, etc.) has its own metrics.
*   **Per-member run**: Each team member run has its own metrics. You can make member runs available on the `TeamRunOutput` by setting `store_member_responses=True`,
*   **Team-level**: The `TeamRunOutput` aggregates metrics across all team leader and team member messages.
*   **Session-level**: Aggregated metrics across all runs in the session, for both the team leader and all team members.

## Example Usage

Suppose you have a team that performs some tasks and you want to analyze the metrics after running it. Here’s how you can access and print the metrics:

    from typing import Iterator
    
    from agno.agent import Agent, RunOutput
    from agno.models.openai import OpenAIChat
    from agno.team.team import Team
    from agno.tools.duckduckgo import DuckDuckGoTools
    from agno.utils.pprint import pprint_run_response
    from rich.pretty import pprint
    
    # Create team members
    web_searcher = Agent(
        name="Stock Searcher",
        model=OpenAIChat(id="gpt-5-mini"),
        role="Searches the web for information.",
        tools=[DuckDuckGoTools()],
    )
    
    # Create the team
    team = Team(
        name="Web Research Team",
        model=OpenAIChat(id="gpt-5-mini"),
        members=[web_searcher],
        markdown=True,
        store_member_responses=True,
    )
    
    # Run the team
    run_response: TeamRunOutput = team.run(
        "What is going on in the world?"
    )
    pprint_run_response(run_response, markdown=True)
    
    # Print team leader message metrics
    print("---" * 5, "Team Leader Message Metrics", "---" * 5)
    if run_response.messages:
        for message in run_response.messages:
            if message.role == "assistant":
                if message.content:
                    print(f"Message: {message.content}")
                elif message.tool_calls:
                    print(f"Tool calls: {message.tool_calls}")
                print("---" * 5, "Metrics", "---" * 5)
                pprint(message.metrics)
                print("---" * 20)
    
    # Print aggregated team leader metrics
    print("---" * 5, "Aggregated Metrics of Team Agent", "---" * 5)
    pprint(run_response.metrics)
    
    # Print team leader session metrics
    print("---" * 5, "Session Metrics", "---" * 5)
    pprint(team.get_session_metrics().to_dict())
    
    # Print team member message metrics
    print("---" * 5, "Team Member Message Metrics", "---" * 5)
    if run_response.member_responses:
        for member_response in run_response.member_responses:
            if member_response.messages:
                for message in member_response.messages:
                    if message.role == "assistant":
                        if message.content:
                            print(f"Member Message: {message.content}")
                        elif message.tool_calls:
                            print(f"Member Tool calls: {message.tool_calls}")
                        print("---" * 5, "Member Metrics", "---" * 5)
                        pprint(message.metrics)
                        print("---" * 20)
    

You’ll see the outputs with following information:

*   `input_tokens`: The number of tokens sent to the model.
*   `output_tokens`: The number of tokens received from the model.
*   `total_tokens`: The sum of `input_tokens` and `output_tokens`.
*   `audio_input_tokens`: The number of tokens sent to the model for audio input.
*   `audio_output_tokens`: The number of tokens received from the model for audio output.
*   `audio_total_tokens`: The sum of `audio_input_tokens` and `audio_output_tokens`.
*   `cache_read_tokens`: The number of tokens read from the cache.
*   `cache_write_tokens`: The number of tokens written to the cache.
*   `reasoning_tokens`: The number of tokens used for reasoning.
*   `duration`: The duration of the run in seconds.
*   `time_to_first_token`: The time taken until the first token was generated.
*   `provider_metrics`: Any provider-specific metrics.

## Developer Resources

*   View the [TeamRunOutput schema]()
*   View the [Metrics schema]()
*   View [Cookbook]()

Was this page helpful?

YesNo



