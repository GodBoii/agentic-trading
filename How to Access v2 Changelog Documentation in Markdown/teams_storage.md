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

