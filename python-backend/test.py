from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from dotenv import load_dotenv
from agno.tools.hackernews import HackerNewsTools
from agno.tools.newspaper import NewspaperTools

load_dotenv()

agent = Agent(
    model=OpenRouter(id="deepseek/deepseek-v4.1-flash"),
    tools=[NewspaperTools()],
    debug_mode=True
    )

agent.print_response("top Bombay stock exchange related news", markdown=True)
