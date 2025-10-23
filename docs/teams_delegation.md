# Delegation - Agno

Search...

Ctrl K

A `Team` internally has a team-leader agent that delegates tasks to the members. When you call `run` or `arun` on a team, the team leader agent uses a model to determine which member to delegate the task to. The basic flow is:

1.  The team receives user input
2.  A Team Leader analyzes the input and decides how to break it down into subtasks
3.  The Team Leader delegates specific tasks to appropriate team members
4.  Team members complete their assigned tasks and return their results
5.  The Team Leader synthesizes all outputs into a final, cohesive response

Below are some examples of how to change the behaviour of how tasks are delegated to the members.

## Determine input for members

When a team is run, by default the team leader will determine the “task” to give a specific member. This then becomes the `input` when that member is run. If you set `determine_input_for_members` to `False`, the team leader will send the user-provided input directly to the member agent(s). The team leader still determines the appropriate member to delegate the task to.

This feature is particularly useful when you have specialized agents with distinct expertise areas and want to automatically direct queries to the right specialist.

In the example below, we want to send stuctured pydantic input directly to the member agent. We don’t want the team leader to ingest this input and determine a task to give to the member agent.

1

Create Team

Create a file `determine_input_for_members.py`

determine\_input\_for\_members.py

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
        determine_input_for_members=False,  # The member gets the input directly, without the team leader synthesizing it
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
    

2

Run the team

Install libraries

    pip install openai agno
    

Run the team

    python determine_input_for_members.py
    

## Respond directly

During normal team execution, the team leader will process the responses from the members and return a single response to the user. If instead you want to return the response of members directly, you can set `respond_directly` to `True`.

It can make sense to use this feature in combination with `determine_input_for_members=False`.

1

Create Multi Language Team

Create a file `multi_language_team.py`

multi\_language\_team.py

    from agno.agent import Agent
    from agno.models.anthropic import Claude
    from agno.models.deepseek import DeepSeek
    from agno.models.openai import OpenAIChat
    from agno.team.team import Team
    
    english_agent = Agent(
        name="English Agent",
        role="You can only answer in English",
        model=OpenAIChat(id="gpt-4.5-preview"),
        instructions=[
            "You must only respond in English",
        ],
    )
    
    japanese_agent = Agent(
        name="Japanese Agent",
        role="You can only answer in Japanese",
        model=DeepSeek(id="deepseek-chat"),
        instructions=[
            "You must only respond in Japanese",
        ],
    )
    chinese_agent = Agent(
        name="Chinese Agent",
        role="You can only answer in Chinese",
        model=DeepSeek(id="deepseek-chat"),
        instructions=[
            "You must only respond in Chinese",
        ],
    )
    spanish_agent = Agent(
        name="Spanish Agent",
        role="You can only answer in Spanish",
        model=OpenAIChat(id="gpt-4.5-preview"),
        instructions=[
            "You must only respond in Spanish",
        ],
    )
    
    german_agent = Agent(
        name="German Agent",
        role="You can only answer in German",
        model=Claude("claude-3-5-sonnet-20241022"),
        instructions=[
            "You must only respond in German",
        ],
    )
    multi_language_team = Team(
        name="Multi Language Team",
        model=OpenAIChat("gpt-4.5-preview"),
        respond_directly=True,
        members=[
            english_agent,
            spanish_agent,
            japanese_agent,
            german_agent,
            chinese_agent,
        ],
        markdown=True,
        instructions=[
            "You are a language router that directs questions to the appropriate language agent.",
            "If the user asks in a language whose agent is not a team member, respond in English with:",
            "\"I can only answer in the following languages: English, Spanish, Japanese, and German. Please ask your question in one of these languages.\"",
            "Always check the language of the user\"s input before routing to an agent.",
            "For unsupported languages like Italian, respond in English with the above message.",
        ],
        show_members_responses=True,
    )
    
    
    # Ask \"How are you?\" in all supported languages
    multi_language_team.print_response(
        "How are you?", stream=True  # English
    )
    
    multi_language_team.print_response(
        "你好吗？", stream=True  # Chinese
    )
    
    multi_language_team.print_response(
        "お元気ですか?", stream=True  # Japanese
    )
    

2

Run the team

Install libraries

    pip install openai agno
    

Run the team

    python multi_language_team.py
    

This is not compatible with `delegate_task_to_all_members`.

## Delegate task to all members

When you set `delegate_task_to_all_members` to `True`, the team leader will delegate the task to all members simultaneously, instead of one by one. When running async (using `arun`) members will run concurrently.

1

Create a collaborate mode team

Create a file `discussion_team.py`

discussion\_team.py

    import asyncio
    from textwrap import dedent
    
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.team.team import Team
    from agno.tools.arxiv import ArxivTools
    from agno.tools.duckduckgo import DuckDuckGoTools
    from agno.tools.googlesearch import GoogleSearchTools
    from agno.tools.hackernews import HackerNewsTools
    from pydantic import BaseModel, Field
    
    
    class ResearchTopic(BaseModel):
        """Structured research topic with specific requirements."""
    
        topic: str = Field(description="The main research topic")
        focus_areas: List[str] = Field(description="Specific areas to focus on")
        target_audience: str = Field(description="Who this research is for")
        sources_required: int = Field(description="Number of sources needed", default=5)
    
    
    class ResearchReport(BaseModel):
        """Structured research report summarizing findings."""
    
        title: str = Field(description="Title of the research report")
        summary: str = Field(description="Concise summary of the research")
        key_findings: List[str] = Field(description="List of key findings")
        recommendations: List[str] = Field(description="Actionable recommendations")
        sources: List[str] = Field(description="List of sources consulted")
    
    
    # Define agents for different research aspects
    arxiv_agent = Agent(
        name="Arxiv Agent",
        model=OpenAIChat(id="gpt-5-mini"),
        tools=[ArxivTools()],
        role="Search and summarize academic papers from Arxiv",
        instructions=[
            "Search Arxiv for relevant academic papers",
            "Extract key findings and methodologies",
            "Summarize papers concisely",
        ],
    )
    
    duckduckgo_agent = Agent(
        name="DuckDuckGo Agent",
        model=OpenAIChat(id="gpt-5-mini"),
        tools=[DuckDuckGoTools()],
        role="Perform general web searches and extract information",
        instructions=[
            "Use DuckDuckGo to search for information",
            "Extract relevant snippets and URLs",
            "Summarize findings clearly",
        ],
    )
    
    googlesearch_agent = Agent(
        name="GoogleSearch Agent",
        model=OpenAIChat(id="gpt-5-mini"),
        tools=[GoogleSearchTools()],
        role="Perform targeted Google searches and extract information",
        instructions=[
            "Use Google Search for in-depth information retrieval",
            "Identify authoritative sources",
            "Synthesize information from multiple search results",
        ],
    )
    
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
    
    # Create a collaborative research team
    discussion_team = Team(
        name="Collaborative Research Team",
        model=OpenAIChat(id="gpt-5-mini"),
        members=[
            arxiv_agent,
            duckduckgo_agent,
            googlesearch_agent,
            hackernews_agent,
        ],
        delegate_task_to_all_members=True,  # All members get the same task
        instructions=[
            "Collaboratively research the given topic using your specialized tools.",
            "Each member should contribute their unique findings.",
            "Synthesize all information into a comprehensive research report.",
        ],
        output_schema=ResearchReport,  # Ensure structured output
        show_members_responses=True,
    )
    
    
    async def main():
        research_topic = ResearchTopic(
            topic="Impact of AI on Software Development",
            focus_areas=["Code Generation", "Testing Automation", "Developer Productivity"],
            target_audience="Software Engineering Leaders",
            sources_required=10,
        )
        response = await discussion_team.arun(input=research_topic)
        print(response.output.model_dump_json(indent=2))
    
    
    if __name__ == "__main__":
        asyncio.run(main())
    

2

Run the team

Install libraries

    pip install openai agno arxiv pyPDF googlesearch-python pycountry
    

Run the team

    python discussion_team.py
    

## Custom delegation

If you want to have full control over how tasks are delegated to the members, you can provide a custom `delegation_manager` to the team. The `DelegationManager` class is responsible for handling the model used to determine which member to delegate the task to. You can adjust it to personalize how tasks are delegated:

    from agno.team import Team
    from agno.team.delegation import DelegationManager
    from agno.models.openai import OpenAIChat
    
    # Setup your Delegation Manager, to adjust how tasks are delegated
    delegation_manager = DelegationManager(
        # Select the model used for delegation. If not specified, the team\"s model is used by default.
        model=OpenAIChat(id="gpt-5-mini"),
        # You can also overwrite the prompt used for delegation
        delegation_prompt="Determine which member is best suited to handle the following task:",
    )
    
    # Now provide the adjusted Delegation Manager to your Team
    team = Team(
      members=[],
      delegation_manager=delegation_manager,
    )

See the [Team reference]() for more details.

Was this page helpful? Yes No

Context Engineering Input and Output

github discord youtube website

Powered by Mintlify

