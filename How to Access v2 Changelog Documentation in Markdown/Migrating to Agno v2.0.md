# Migrating to Agno v2.0

Search...

Ctrl K

If you have questions during your migration, we can help! Find us on [Discord]() or [Discourse]()

Reference the [v2.0 Changelog]() for the full list of changes.

## Installing Agno v2

If you are already using Agno, you can upgrade to v2 by running:

    pip install -U agno
    

Otherwise, you can install the latest version of Agno v2 by running:

    pip install agno
    

## Migrating your Agno DB

If you used our `Storage` or `Memory` functionalities to store Agent sessions and memories in your database, you can start by migrating your tables. Use our migration script: [`libs/agno/scripts/migrate_to_v2.py`]() The script supports PostgreSQL, MySQL, SQLite, and MongoDB. Update the database connection settings in the script and run it. Notice:

*   The script won’t cleanup the old tables, in case you still need them.
*   The script is idempotent. If something goes wrong or if you stop it mid-run, you can run it again.
*   Metrics are automatically converted from v1 to v2 format.

## Migrating your Agno code

Each section here covers a specific framework domain, with before and after examples and detailed explanations where needed.

### 1\. Agents and Teams

[Agents]() and [Teams]() are the main building blocks in the Agno framework. Below are some of the v2 updates we have made to the `Agent` and `Team` classes: 1.1. Streaming responses with `arun` now returns an `AsyncIterator`, not a coroutine. This is how you consume the resulting events now, when streaming a run:

v2\_arun.py

    async for event in agent.arun(...):
        ...
    

1.2. The `RunResponse` class is now `RunOutput`. This is the type of the results you get when running an Agent:

v2\_run\_output.py

    from agno.run.agent import RunOutput
    
    run_output: RunOutput = agent.run(...)
    

1.3. The events you get when streaming an Agent result have been renamed:

*   `RunOutputStartedEvent` → `RunStartedEvent`
*   `RunOutputCompletedEvent` → `RunCompletedEvent`
*   `RunOutputErrorEvent` → `RunErrorEvent`
*   `RunOutputCancelledEvent` → `RunCancelledEvent`
*   `RunOutputContinuedEvent` → `RunContinuedEvent`
*   `RunOutputPausedEvent` → `RunPausedEvent`
*   `RunOutputContentEvent` → `RunContentEvent`

1.4. Similarly, for Team output events:

*   `TeamRunOutputStartedEvent` → `TeamRunStartedEvent`
*   `TeamRunOutputCompletedEvent` → `TeamRunCompletedEvent`
*   `TeamRunOutputErrorEvent` → `TeamRunErrorEvent`
*   `TeamRunOutputCancelledEvent` → `TeamRunCancelledEvent`
*   `TeamRunOutputContentEvent` → `TeamRunContentEvent`

1.5. The `add_state_in_messages` parameter has been deprecated. Variables in instructions are now resolved automatically by default. 1.6. The `context` parameter has been renamed to `dependencies`. This is how it looked like on v1:

v1\_context.py

    from agno.agent import Agent
    
    agent = Agent(
        context={"top_stories": get_top_hackernews_stories},
        instructions="Here are the top stories: {top_stories}",
        add_state_in_messages=True,
    )
    

This is how it looks like now, on v2:

v2\_dependencies.py

    from agno.agent import Agent
    
    agent = Agent(
        dependencies={"top_stories": get_top_hackernews_stories},
        instructions="Here are the top stories: {top_stories}",
        # resolve_in_context=True by default - no need to set add_state_in_messages
    )
    

See the full list of changes in the [Agent Updates]() section of the changelog.

### 2\. Storage

Storage is used to persist Agent sessions, state and memories in a database. This is how Storage looks like on v1:

v1\_storage.py

    from agno.agent import Agent
    from agno.storage.sqlite import SqliteStorage
    
    storage = SqliteStorage(table_name="agent_sessions", db_file="agno.db", mode="agent")
    
    agent = Agent(storage=storage)
    

These are the changes we have made for v2: 2.1. The `Storage` classes have moved from `agno/storage` to `agno/db`. We will now refer to them as our `Db` classes. 2.2. The `mode` parameter has been deprecated. The same instance can now be used by Agents, Teams and Workflows.

v2\_storage.py

    from agno.agent import Agent
    from agno.db.sqlite import SqliteDb
    
    db = SqliteDb(db_file="agno.db")
    
    agent = Agent(db=db)
    

2.3. The `table_name` parameter has been deprecated. One instance now handles multiple tables, you can define their names individually.

v2\_storage\_table\_names.py

    db = SqliteDb(db_file="agno.db", sessions_table="your_sessions_table_name", ...)
    

These are all the supported tables, each used to persist data related to a specific domain:

v2\_storage\_all\_tables.py

    db = SqliteDb(
        db_file="agno.db",
        # Table to store your Agent, Team and Workflow sessions and runs
        session_table="your_session_table_name",
        # Table to store all user memories
        memory_table="your_memory_table_name",
        # Table to store all metrics aggregations
        metrics_table="your_metrics_table_name",
        # Table to store all your evaluation data
        eval_table="your_evals_table_name",
        # Table to store all your knowledge content
        knowledge_table="your_knowledge_table_name",
    )
    

2.4. Previously running a `Team` would create a team session and sessions for every team member participating in the run. Now, only the `Team` session is created. The runs for the team leader and all members can be found in the `Team` session.

v2\_storage\_team\_sessions.py

    team.run(...)
    
    team_session = team.get_latest_session()
    
    # The runs for the team leader and all team members are here
    team_session.runs
    

See more changes in the [Storage Updates]() section of the changelog.

### 3\. Memory

Memory gives an Agent the ability to recall relevant information. This is how Memory looks like on V1:

v1\_memory.py

    from agno.agent import Agent
    from agno.memory.v2.db.sqlite import SqliteMemoryDb
    from agno.memory.v2.memory import Memory
    
    memory_db = SqliteMemoryDb(table_name="memory", db_file="agno.db")
    memory = Memory(db=memory_db)
    
    agent = Agent(memory=memory)
    

These are the changes we have made for v2: 3.1. The `MemoryDb` classes have been deprecated. The main `Db` classes are to be used. 3.2. The `Memory` class has been deprecated. You now just need to set `enable_user_memories=True` on an Agent with a `db` for Memory to work.

v2\_memory.py

    from agno.agent import Agent
    from agno.db.sqlite import SqliteDb
    
    db = SqliteDb(db_file="agno.db")
    
    agent = Agent(db=db, enable_user_memories=True)
    

3.3. The generated memories will be stored in the `memories_table`. By default, the `agno_memories` will be used. It will be created if needed. You can also set the memory table like this:

v2\_memory\_set\_table.py

    db = SqliteDb(db_file="agno.db", memory_table="your_memory_table_name")
    

3.4. The methods you previously had access to through the Memory class, are now direclty available on the relevant `db` object. For example:

v2\_memory\_db\_methods.py

    agent.get_user_memories(user_id="123")
    

You can find examples for other all other databases and advanced scenarios in the [examples]() section.

See more changes in the [Memory Updates]() section of the changelog.

### 4\. Knowledge

Knowledge gives an Agent the ability to search and retrieve relevant, domain-specific information from a knowledge base. These are the changes we have made for v2: 4.1. `AgentKnowledge` has been deprecated in favor of the new `Knowledge` class. Along with this, all of the child classes that used `AgentKnowledge` as a base have been removed. Their capabilities are now supported by default in `Knowledge`. This also means that the correct reader for the content that you are adding is now selected automatically, with the option to override it at any time. 4.2. The `load()` method and its variations have been replaced by `add_content()` and `add_content_async()`:

v1\_knowledge.py

    from agno.agent import Agent
    from agno.knowledge import AgentKnowledge
    
    knowledge = AgentKnowledge()
    knowledge.load("path/to/file.pdf")
    
    agent = Agent(knowledge=knowledge)
    

v2\_knowledge.py

    from agno.agent import Agent
    from agno.knowledge import Knowledge
    
    knowledge = Knowledge()
    knowledge.add_content("path/to/file.pdf")
    
    agent = Agent(knowledge=knowledge)
    

4.3. The `Knowledge` class now supports `async` operations for adding content. This is a major performance improvement when adding large amounts of content to your knowledge base:

v2\_knowledge\_async.py

    await knowledge.add_content_async("path/to/file.pdf")
    

4.4. The `Knowledge` class now supports a `db` parameter to persist the knowledge base. This is how it looks like:

v2\_knowledge\_db.py

    from agno.agent import Agent
    from agno.knowledge import Knowledge
    from agno.db.sqlite import SqliteDb
    
    db = SqliteDb(db_file="agno.db")
    knowledge = Knowledge(db=db)
    
    agent = Agent(knowledge=knowledge)
    

4.5. The `Knowledge` class now supports a `vector_db` parameter to use a vector database for similarity search. This is how it looks like:

v2\_knowledge\_vector\_db.py

    from agno.agent import Agent
    from agno.knowledge import Knowledge
    from agno.db.sqlite import SqliteDb
    from agno.vector_db.chroma import ChromaDb
    
    db = SqliteDb(db_file="agno.db")
    vector_db = ChromaDb(db_file="agno.db")
    knowledge = Knowledge(db=db, vector_db=vector_db)
    
    agent = Agent(knowledge=knowledge)
    

See more changes in the [Knowledge Updates]() section of the changelog.

### 5\. Workflows

Workflows are used to orchestrate multiple Agents and Tools to achieve a complex goal. This is how Workflows look like on v1:

v1\_workflow.py

    from agno.workflow import Workflow
    
    workflow = Workflow(
        agents=["agent1", "agent2"],
        tools=["tool1", "tool2"],
        instructions="Orchestrate agents and tools to achieve a goal.",
    )
    

These are the changes we have made for v2: 5.1. The `Workflow` class now supports a `db` parameter to persist the workflow sessions and runs. This is how it looks like:

v2\_workflow\_db.py

    from agno.workflow import Workflow
    from agno.db.sqlite import SqliteDb
    
    db = SqliteDb(db_file="agno.db")
    workflow = Workflow(db=db)
    

5.2. The `Workflow` class now supports `async` operations for running workflows. This is a major performance improvement when running complex workflows:

v2\_workflow\_async.py

    await workflow.arun(...)
    

5.3. The `Workflow` class now supports a `workflow_id` parameter to identify the workflow. This is how it looks like:

v2\_workflow\_id.py

    workflow = Workflow(workflow_id="my_workflow")
    

See more changes in the [Workflow Updates]() section of the changelog.

### 6\. AgentOS

AgentOS is a system for hosting agents, teams and workflows as a production-ready API. This is how AgentOS looks like on v1:

v1\_agentos.py

    from agno.agentos import AgentOS
    
    agent_os = AgentOS()
    agent_os.add_agent("my_agent", agent)
    agent_os.serve(port=8000)
    

These are the changes we have made for v2: 6.1. The `AgentOS` class now supports a `db` parameter to persist the AgentOS sessions and runs. This is how it looks like:

v2\_agentos\_db.py

    from agno.agentos import AgentOS
    from agno.db.sqlite import SqliteDb
    
    db = SqliteDb(db_file="agno.db")
    agent_os = AgentOS(db=db)
    

6.2. The `AgentOS` class now supports `async` operations for running agents, teams and workflows. This is a major performance improvement when running complex operations:

v2\_agentos\_async.py

    await agent_os.arun_agent("my_agent", ...)
    

6.3. The `AgentOS` class now supports a `get_app()` method to get the FastAPI app. This is how it looks like:

v2\_agentos\_get\_app.py

    app = agent_os.get_app()
    

6.4. The `AgentOS` class now supports a `serve()` method to serve the FastAPI app. This is how it looks like:

v2\_agentos\_serve.py

    agent_os.serve(port=8000)
    

Migration Steps

1.  Update imports: Replace app imports with interface imports
2.  Use AgentOS: Wrap agents with `AgentOS` and specify interfaces
3.  Update serving: Use `agent_os.serve()` instead of `app.serve()`

### 8\. Playground -> AgentOS

Our `Playground` has been deprecated. Our new `AgentOS` offering will substitute all usecases.

See [AgentOS]() for more details!

Was this page helpful? Yes No

Agno v2.0 Changelog Workflows 2.0 Migration Guide

github discord youtube website

Powered by Mintlify

