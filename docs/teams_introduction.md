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

