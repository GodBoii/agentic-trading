from agno.agent import Agent
from agno.models.groq import Groq
from dotenv import load_dotenv
from agno.tools.hackernews import HackerNewsTools
from agno.tools.newspaper import NewspaperTools

load_dotenv()

agent = Agent(
    model=Groq(id="openai/gpt-oss-120b"),
    tools=[NewspaperTools()],
    debug_mode=True
    )

agent.print_response("top Bombay stock exchange related news", markdown=True)