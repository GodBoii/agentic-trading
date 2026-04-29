# Shared State - Agno

Search...

Ctrl K

Team Session State enables sophisticated state management across teams of agents. Teams often need to coordinate on shared information.

Shared state propagates through nested team structures as well

## How to use Shared State

You can set the `session_state` parameter on `Team` to share state between the team leader and team members. This state is available to all team members and is synchronized between them. For example:

    team = Team(
        members=[agent1, agent2, agent3],
        session_state={"shopping_list": []},
    )
    

Members can access the shared state using the `session_state` attribute in tools. For example:

    def add_item(session_state, item: str) -> str:
        """Add an item to the shopping list and return confirmation.
    
        Args:
            item (str): The item to add to the shopping list.
        """
        # Add the item if it\\'s not already in the list
        if item.lower() not in [
            i.lower() for i in session_state["shopping_list"]
        ]:
            session_state["shopping_list"].append(item)
            return f"Added \'{item}\' to the shopping list"
        else:
            return f"\'{item}\' is already in the shopping list"
    

The `session_state` variable is automatically passed to the tool as an argument. Any updates to it is automatically reflected in the shared state.

### Example

Here’s a simple example of a team managing a shared shopping list:

team\_session\_state.py

    from agno.models.openai import OpenAIChat
    from agno.agent import Agent
    from agno.team import Team
    
    
    # Define tools that work with shared team state
    def add_item(session_state, item: str) -> str:
        """Add an item to the shopping list."""
        if item.lower() not in [
            i.lower() for i in session_state["shopping_list"]
        ]:
            session_state["shopping_list"].append(item)
            return f"Added \'{item}\' to the shopping list"
        else:
            return f"\'{item}\' is already in the shopping list"
    
    
    def remove_item(session_state, item: str) -> str:
        """Remove an item from the shopping list."""
        for i, list_item in enumerate(session_state["shopping_list"]):
            if list_item.lower() == item.lower():
                session_state["shopping_list"].pop(i)
                return f"Removed \'{list_item}\' from the shopping list"
        
        return f"\'{item}\' was not found in the shopping list"
    
    
    # Create an agent that manages the shopping list
    shopping_agent = Agent(
        name="Shopping List Agent",
        role="Manage the shopping list",
        model=OpenAIChat(id="gpt-5-mini"),
        tools=[add_item, remove_item],
    )
    
    
    # Define team-level tools
    def list_items(session_state) -> str:
        """List all items in the shopping list."""
        # Access shared state (not private state)
        shopping_list = session_state["shopping_list"]
        
        if not shopping_list:
            return "The shopping list is empty."
        
        items_text = "\n".join([f"- {item}" for item in shopping_list])
        return f"Current shopping list:\n{items_text}"
    
    
    def add_chore(session_state, chore: str) -> str:
        """Add a completed chore to the team\\'s private log."""
        # Access team\\'s private state
        if "chores" not in session_state:
            session_state["chores"] = []
        
        session_state["chores"].append(chore)
        return f"Logged chore: {chore}"
    
    
    # Create a team with both shared and private state
    shopping_team = Team(
        name="Shopping Team",
        model=OpenAIChat(id="gpt-5-mini"),
        members=[shopping_agent],
        session_state={"shopping_list": [], "chores": []},
        tools=[list_items, add_chore],
        instructions=[
            "You manage a shopping list.",
            "Forward add/remove requests to the Shopping List Agent.",
            "Use list_items to show the current list.",
            "Log completed tasks using add_chore.",
        ],
    )
    
    # Example usage
    shopping_team.print_response("Add milk, eggs, and bread", stream=True)
    print(f"Shared state: {shopping_team.get_session_state()}")
    
    shopping_team.print_response("What\\'s on my list?", stream=True)
    
    shopping_team.print_response("I got the eggs", stream=True)
    print(f"Shared state: {shopping_team.get_session_state()}")
    

Notice how shared tools use `session_state`, which allows state to propagate and persist across the entire team — even for subteams within the team. This ensures consistent shared state for all members.

See a full example [here]().

## Agentic Session State

Agno provides a way to allow the team and team members to automatically update the shared session state. Simply set the `enable_agentic_state` parameter to `True`.

agentic\_session\_state.py

    from agno.agent import Agent
    from agno.db.sqlite import SqliteDb
    from agno.models.openai import OpenAIChat
    from agno.team.team import Team
    
    db = SqliteDb(db_file="tmp/agents.db")
    shopping_agent = Agent(
        name="Shopping List Agent",
        role="Manage the shopping list",
        model=OpenAIChat(id="gpt-5-mini"),
        db=db,
        add_session_state_to_context=True,  # Required so the agent is aware of the session state
        enable_agentic_state=True,
    )
    
    team = Team(
        members=[shopping_agent],
        session_state={"shopping_list": []},
        db=db,
        add_session_state_to_context=True,  # Required so the team is aware of the session state
        enable_agentic_state=True,
        description="You are a team that manages a shopping list and chores",
        show_members_responses=True,
    )
    
    
    team.print_response("Add milk, eggs, and bread to the shopping list")
    
    team.print_response("I picked up the eggs, now what\\'s on my list?")
    
    print(f"Session state: {team.get_session_state()}")
    

Don’t forget to set `add_session_state_to_context=True` to make the session state available to the team’s context.

## Using state in instructions

You can reference variables from the session state in your instructions.

Don’t use the f-string syntax in the instructions. Directly use the `{key}` syntax, Agno substitutes the values for you.

state\_in\_instructions.py

    from agno.team.team import Team
    
    team = Team(
        members=[],
        # Initialize the session state with a variable
        session_state={"user_name": "John"},
        instructions="Users name is {user_name}",
        markdown=True,
    )
    
    team.print_response("What is my name?", stream=True)
    

## Changing state on run

When you pass `session_id` to the team on `team.run()`, it will switch to the session with the given `session_id` and load any state that was set on that session. This is useful when you want to continue a session for a specific user.

changing\_state\_on\_run.py

    from agno.team.team import Team
    from agno.models.openai import OpenAIChat
    from agno.db.in_memory import InMemoryDb
    
    team = Team(
        db=InMemoryDb(),
        model=OpenAIChat(id="gpt-5-mini"),
        members=[],
        instructions="Users name is {user_name} and age is {age}",
    )
    
    # Sets the session state for the session with the id "user_1_session_1"
    team.print_response("What is my name?", session_id="user_1_session_1", user_id="user_1", session_state={"user_name": "John", "age": 30})
    
    # Will load the session state from the session with the id "user_1_session_1"
    team.print_response("How old am I?", session_id="user_1_session_1", user_id="user_1")
    
    # Sets the session state for the session with the id "user_2_session_1"
    team.print_response("What is my name?", session_id="user_2_session_1", user_id="user_2", session_state={"user_name": "Jane", "age": 25})
    
    # Will load the session state from the session with the id "user_2_session_1"
    team.print_response("How old am I?", session_id="user_2_session_1", user_id="user_2")
    

## Developer Resources

*   View the [Team schema]()
*   View [Cookbook]()

Was this page helpful? Yes No

Dependencies Storage

github discord youtube website

Powered by Mintlify

