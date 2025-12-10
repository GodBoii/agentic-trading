# Documentation from Agno Teams

## Document 1: Teams Overview

# Teams Overview

A Team is a collection of Agents (or other sub-teams) that work together to accomplish tasks. A `Team` has a list of `members` that can be instances of either `Agent` or `Team`. A team can be visualized as a tree structure, where the team leader delegates tasks to sub-teams or directly to agents. The top level of the `Team` is called the team leader. 

Below is a minimal example of a language-routing team with two agents and one sub-team:

```python
from agno.team import Team
from agno.agent import Agent

team = Team(members=[
    Agent(name="English Agent", role="You answer questions in English"),
    Agent(name="Chinese Agent", role="You answer questions in Chinese"),
    Team(
      name="Germanic Team", 
      role="You coordinate the team members to answer questions in German and Dutch",
      members=[
        Agent(name="German Agent", role="You answer questions in German"),
        Agent(name="Dutch Agent", role="You answer questions in Dutch"),
      ],
    ),
])
```

The team leader delegates tasks to members depending on the role of the members and the nature of the tasks. See the [Delegation](https://docs.agno.com/basics/teams/delegation) guide for more details. 

As with agents, teams support the following features:

* **Model:** Set the model that is used by the team leader to delegate tasks to the team members.
* **Instructions:** Instruct the team leader on how to solve problems. The names, descriptions and roles of team members are automatically provided to the team leader.
* **Database:** The Teams session history and state is stored in a database. This enables your team to continue conversations from where they left off, enabling multi-turn, long-running conversations.
* **Reasoning:** Enables the team leader to think before responding or delegating tasks to team members, and analyze the results of team members responses.
* **Knowledge:** If the team needs to search for information, you can add a knowledge base to the team. This is accessible to the team leader.
* **Memory:** Gives Teams the ability to store and recall information from previous interactions, allowing them to learn user preferences and personalize their responses.
* **Tools:** If the team leader needs to be able to use tools directly, you can add tools to the team.

## When should you use Teams?

When should you use Teams? The general guideline is to have Agents that are narrow in scope. When you have a complex task that requires a variety of tools or a long list of steps, a Team of single-purpose agents would be a good fit. In addition, if a single agents context limit gets easily exceeded, because of the complexity of the task, a Team would address this by keeping a single agents context small, becaues it only addresses a part of the task.

## Guides

## Developer Resources

* View the [`Team` schema reference](https://docs.agno.com/reference/teams/team)
* View [Use-cases](https://docs.agno.com/examples/use-cases/teams)
* View [Usage Examples](https://docs.agno.com/basics/teams/usage)
* View a [Teams Cookbook](https://github.com/agno-agi/agno/tree/main/cookbook/teams/README.md)

---

## Document 2: Building Teams

# Building Teams

To build effective teams, start simple just a model, team members, and instructions. Once that works, add more functionality as needed. Here's a minimal example of a team with specialized agents:

```python
from agno.team import Team
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGoTools

# Create specialized agents
news_agent = Agent(
    id="news-agent",
    name="News Agent",
    role="Get the latest news and provide summaries",
    tools=[DuckDuckGoTools()]
)

weather_agent = Agent(
    id="weather-agent",
    name="Weather Agent",
    role="Get weather information and forecasts",
    tools=[DuckDuckGoTools()]
)

# Create the team
team = Team(
    name="News and Weather Team",
    members=[news_agent, weather_agent],
    model=OpenAIChat(id="gpt-4o"),
    instructions="Coordinate with team members to provide comprehensive information. Delegate tasks based on the user's request."
)

team.print_response("What's the latest news and weather in Tokyo?", stream=True)
```

## Run your Team

When running your team, use the `Team.print_response()` method to print the response in the terminal. You can pass `show_members_responses=True` to also print the responses from the team members. For example:

```python
team.print_response("What's the latest news and weather in Tokyo?")
```

This is only for development purposes and not recommended for production use. In production, use the `Team.run()` or `Team.arun()` methods. For example:

```python
from typing import Iterator
from agno.team import Team
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.utils.pprint import pprint_run_response

news_agent = Agent(name="News Agent", role="Get the latest news", tools=[DuckDuckGoTools()])
weather_agent = Agent(name="Weather Agent", role="Get the weather for the next 7 days", tools=[DuckDuckGoTools()])

team = Team(
    name="News and Weather Team",
    members=[news_agent, weather_agent],
    model=OpenAIChat(id="gpt-4o")
)

# Run team and return the response as a variable
response = team.run("What is the weather in Tokyo?")
# Print the response
print(response.content)

################ STREAM RESPONSE #################
stream = team.run("What is the weather in Tokyo?", stream=True)
for chunk in stream:
    print(chunk.content, end="", flush=True)

# ################ STREAM AND PRETTY PRINT #################
stream = team.run("What is the weather in Tokyo?", stream=True)
pprint_run_response(stream, markdown=True)
```

### Modify what is show on the terminal

When using `print_response`, only the team tool calls (typically all of the delegation to members) are printed. If you want to print the responses from the members, you can use the `show_members_responses` parameter.

```python
...

team = Team(
    name="News and Weather Team", 
    members=[news_agent, weather_agent],
    model=OpenAIChat(id="gpt-4o")
    show_members_responses=True,
)

team.print_response("What is the weather in Tokyo?")
```

## The Passthrough-Team Pattern

It is a common pattern to have a team that decides which member to delegate the request to, and then passes the request to the team member without any modification, and also applies no processing to the response before returning it to the user. I.e. this team is a passthrough team (or router team). In that case the team leader is effectively bypassed and all communication is directly with a team member. See the [Passthrough Teams](https://docs.agno.com/basics/teams/delegation#passthrough-teams) section for more details.

## Next Steps

Next, continue building your team by adding functionality as needed. Common questions:

* **How do I run my team?** → See the [running teams](https://docs.agno.com/basics/teams/running-teams) documentation.
* **How do I add history to my team?** → See the [chat history](https://docs.agno.com/basics/chat-history/team/overview) documentation.
* **How do I manage sessions?** → See the [sessions](https://docs.agno.com/basics/sessions/overview) documentation.
* **How do I manage input and capture output?** → See the [input and output](https://docs.agno.com/basics/input-output/overview) documentation.
* **How do I manage the team context?** → See the [context engineering](https://docs.agno.com/basics/context/team) documentation.
* **How do I add knowledge?** → See the [knowledge](https://docs.agno.com/basics/knowledge/overview) documentation.
* **How do I add guardrails?** → See the [guardrails](https://docs.agno.com/basics/guardrails/overview) documentation.
* **How do I cache responses during development?** → See the [response caching](https://docs.agno.com/basics/models/cache-response) documentation.

---

I've successfully retrieved and formatted both documentation pages from Agno's Teams documentation. The first document provides an overview of what Teams are and when to use them, while the second document shows how to build and run teams with practical code examples.