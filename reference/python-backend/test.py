from agno.agent import Agent, RunOutput 
from PIL import Image
from agno.models.google import Gemini
from agno.tools.api import CustomApiTools
from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.websearch import WebSearchTools
from agno.models.groq import Groq
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

agent = Agent(
    model=OpenRouter(id="sourceful/riverflow-v2-fast"),
)
run_response = agent.run("Make me an image of a cat in a tree.")

if run_response and isinstance(run_response, RunOutput) and run_response.images:
    for image_response in run_response.images:
        image_bytes = image_response.content
        if image_bytes:
            image = Image.open(BytesIO(image_bytes))
            image.show()
            # Save the image to a file
            # image.save("generated_image.png")
else:
    print("No images found in run response")