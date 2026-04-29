# Agno Multimodal Documentation




# Multimodal Agents Overview




# Multimodal Agents

Search...

Ctrl K

Agno agents support text, image, audio and video inputs and can generate text, image, audio and video outputs. For a complete overview, please checkout the [compatibility matrix]().

To get started, feel free to checkout the [multimodal examples]().

## Multimodal inputs to an agent

Let’s create an agent that can understand images and make tool calls as needed

### Agent with Image Understanding

image\_agent.py

    from agno.agent import Agent
    from agno.media import Image
    from agno.models.openai import OpenAIChat
    from agno.tools.duckduckgo import DuckDuckGoTools
    
    agent = Agent(
        model=OpenAIChat(id="gpt-5-mini"),
        tools=[DuckDuckGoTools()],
        markdown=True,
    )
    
    agent.print_response(
        "Tell me about this image and give me the latest news about it.",
        images=[
            Image(
                url="https://upload.wikimedia.org/wikipedia/commons/0/0c/GoldenGateBridge-001.jpg"
            )
        ],
        stream=True,
    )

Run the agent:

    python image_agent.py

Similar to images, you can also use audio and video as an input.

### Agent with Audio Understanding

audio\_agent.py

    import base64
    
    import requests
    from agno.agent import Agent, RunOutput  # noqa
    from agno.media import Audio
    from agno.models.openai import OpenAIChat
    
    # Fetch the audio file and convert it to a base64 encoded string
    url = "https://openaiassets.blob.core.windows.net/$web/API/docs/audio/alloy.wav"
    response = requests.get(url)
    response.raise_for_status()
    wav_data = response.content
    
    agent = Agent(
        model=OpenAIChat(id="gpt-5-mini-audio-preview", modalities=["text"]),
        markdown=True,
    )
    agent.print_response(
        "What is in this audio?", audio=[Audio(content=wav_data, format="wav")]
    )

### Agent with Video Understanding

video\_agent.py

    from pathlib import Path
    
    from agno.agent import Agent
    from agno.media import Video
    from agno.models.google import Gemini
    
    agent = Agent(
        model=Gemini(id="gemini-2.0-flash-001"),
        markdown=True,
    )
    
    # Please download "GreatRedSpot.mp4" using
    # wget https://storage.googleapis.com/generativeai-downloads/images/GreatRedSpot.mp4
    video_path = Path(__file__).parent.joinpath("GreatRedSpot.mp4")
    
    agent.print_response("Tell me about this video", videos=[Video(filepath=video_path)])

## Multimodal outputs from an agent

Similar to providing multimodal inputs, you can also get multimodal outputs from an agent. You can either use tools to generate image/audio/video or use the agent’s model to generate them (if the model supports this capability).The following example demonstrates how to generate an image using an OpenAI tool with an agent.

image\_agent.py

    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.tools.openai import OpenAITools
    from agno.utils.media import save_base64_data
    
    agent = Agent(
        model=OpenAIChat(id="gpt-5-mini"),
        tools=[OpenAITools(image_model="gpt-image-1")],
        markdown=True,
    )
    
    response = agent.run(
        "Generate a photorealistic image of a cozy coffee shop interior",
    )
    
    if response.images and response.images[0].content:
        save_base64_data(str(response.images[0].content), "tmp/coffee_shop.png")

The output of the tool generating a media also goes to the model’s input as a message so it has access to the media (image, audio, video) and can use it in the response. For example, if you say “Generate an image of a dog and tell me its color.” the model will have access to the image and can use it to describe the dog’s color in the response in the same run.

### Image Model Response

The following example demonstrates how some models can directly generate images as part of their response.

image\_agent.py

    from io import BytesIO
    
    from agno.agent import Agent, RunOutput  # noqa
    from agno.models.google import Gemini
    from PIL import Image
    
    # No system message should be provided
    agent = Agent(
        model=Gemini(
            id="gemini-2.0-flash-exp-image-generation",
            response_modalities=["Text", "Image"], # This means to generate both images and text
        )
    )
    
    # Print the response in the terminal
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
    

You can find all generated images in the `RunOutput.images` list.

The following example demonstrates how to generate an audio using the ElevenLabs tool with an agent. See [Eleven Labs]() for more details.

audio\_agent.py

    import base64
    
    from agno.agent import Agent
    from agno.models.google import Gemini
    from agno.tools.eleven_labs import ElevenLabsTools
    from agno.utils.media import save_base64_data
    
    audio_agent = Agent(
        model=Gemini(id="gemini-2.5-pro"),
        tools=[
            ElevenLabsTools(
                voice_id="21m00Tcm4TlvDq8ikWAM",
                model_id="eleven_multilingual_v2",
                target_directory="audio_generations",
            )
        ],
        description="You are an AI agent that can generate audio using the ElevenLabs API.",
        instructions=[
            "When the user asks you to generate audio, use the `generate_audio` tool to generate the audio.",
            "You\"ll generate the appropriate prompt to send to the tool to generate audio.",
            "You don\"t need to find the appropriate voice first, I already specified the voice to user."
            "Return the audio file name in your response. Don\"t convert it to markdown.",
            "The audio should be long and detailed.",
        ],
        markdown=True,
    )
    
    response = audio_agent.run(
        "Generate a very long audio of history of french revolution and tell me which subject it belongs to.",
        debug_mode=True,
    )
    
    if response.audio:
        print("Agent response:", response.content)
        base64_audio = base64.b64encode(response.audio[0].content).decode("utf-8")
        save_base64_data(base64_audio, "tmp/french_revolution.mp3")
        print("Successfully saved generated speech to tmp/french_revolution.mp3")
    
    
    audio_agent.print_response("Generate a kick sound effect")
    

### Audio Model Response

The following example demonstrates how some models can directly generate audio as part of their response.

audio\_agent.py

    from agno.agent import Agent, RunOutput
    from agno.models.openai import OpenAIChat
    from agno.utils.audio import write_audio_to_file
    
    agent = Agent(
        model=OpenAIChat(
            id="gpt-5-mini-audio-preview",
            modalities=["text", "audio"],
            audio={"voice": "alloy", "format": "wav"},
        ),
        markdown=True,
    )
    response: RunOutput = agent.run("Tell me a 5 second scary story")
    
    # Save the response audio to a file
    if response.response_audio is not None:
        write_audio_to_file(
            audio=agent.run_response.response_audio.content, filename="tmp/scary_story.wav"
        )
    

The following example demonstrates how to generate a video using `FalTools` with an agent. See [FAL]() for more details.

video\_agent.py

    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.tools.fal import FalTools
    
    fal_agent = Agent(
        name="Fal Video Generator Agent",
        model=OpenAIChat(id="gpt-5-mini"),
        tools=[
            FalTools(
                model="fal-ai/hunyuan-video",
                enable_generate_media=True,
            )
        ],
        description="You are an AI agent that can generate videos using the Fal API.",
        instructions=[
            "When the user asks you to create a video, use the `generate_media` tool to create the video.",
            "Return the URL as raw to the user.",
            "Don\"t convert video URL to markdown or anything else.",
        ],
        markdown=True,
    )
    
    fal_agent.print_response("Generate video of balloon in the ocean")
    
    

## Multimodal inputs and outputs together

You can create agents that can take multimodal inputs and return multimodal outputs. The following example demonstrates how to provide a combination of audio and text inputs to an agent and obtain both text and audio outputs.

### Audio input and Audio output

audio\_agent.py

    import requests
    from agno.agent import Agent
    from agno.media import Audio
    from agno.models.openai import OpenAIChat
    from agno.utils.audio import write_audio_to_file
    from rich.pretty import pprint
    
    # Fetch the audio file and convert it to a base64 encoded string
    url = "https://openaiassets.blob.core.windows.net/$web/API/docs/audio/alloy.wav"
    response = requests.get(url)
    response.raise_for_status()
    wav_data = response.content
    
    agent = Agent(
        model=OpenAIChat(
            id="gpt-5-mini-audio-preview",
            modalities=["text", "audio"],
            audio={"voice": "sage", "format": "wav"},
        ),
        markdown=True,
    )
    
    run_response = agent.run(
        "What\"s in these recording?",
        audio=[Audio(content=wav_data, format="wav")],
    )
    
    if run_response.response_audio is not None:
        pprint(run_response.content)
        write_audio_to_file(
            audio=run_response.response_audio.content, filename="tmp/result.wav"
        )

## Developer Resources

*   View more [Examples]()
*   View [Cookbook]()

Was this page helpful?

YesNo






## Multimodal Agents Overview




# Multimodal Agents

Search...

Ctrl K

Agno agents support text, image, audio and video inputs and can generate text, image, audio and video outputs. For a complete overview, please checkout the [compatibility matrix]().

To get started, feel free to checkout the [multimodal examples]().

## Multimodal inputs to an agent

Let’s create an agent that can understand images and make tool calls as needed

### Agent with Image Understanding

image\_agent.py

    from agno.agent import Agent
    from agno.media import Image
    from agno.models.openai import OpenAIChat
    from agno.tools.duckduckgo import DuckDuckGoTools
    
    agent = Agent(
        model=OpenAIChat(id="gpt-5-mini"),
        tools=[DuckDuckGoTools()],
        markdown=True,
    )
    
    agent.print_response(
        "Tell me about this image and give me the latest news about it.",
        images=[
            Image(
                url="https://upload.wikimedia.org/wikipedia/commons/0/0c/GoldenGateBridge-001.jpg"
            )
        ],
        stream=True,
    )

Run the agent:

    python image_agent.py

Similar to images, you can also use audio and video as an input.

### Agent with Audio Understanding

audio\_agent.py

    import base64
    
    import requests
    from agno.agent import Agent, RunOutput  # noqa
    from agno.media import Audio
    from agno.models.openai import OpenAIChat
    
    # Fetch the audio file and convert it to a base64 encoded string
    url = "https://openaiassets.blob.core.windows.net/$web/API/docs/audio/alloy.wav"
    response = requests.get(url)
    response.raise_for_status()
    wav_data = response.content
    
    agent = Agent(
        model=OpenAIChat(id="gpt-5-mini-audio-preview", modalities=["text"]),
        markdown=True,
    )
    agent.print_response(
        "What is in this audio?", audio=[Audio(content=wav_data, format="wav")]
    )

### Agent with Video Understanding

video\_agent.py

    from pathlib import Path
    
    from agno.agent import Agent
    from agno.media import Video
    from agno.models.google import Gemini
    
    agent = Agent(
        model=Gemini(id="gemini-2.0-flash-001"),
        markdown=True,
    )
    
    # Please download "GreatRedSpot.mp4" using
    # wget https://storage.googleapis.com/generativeai-downloads/images/GreatRedSpot.mp4
    video_path = Path(__file__).parent.joinpath("GreatRedSpot.mp4")
    
    agent.print_response("Tell me about this video", videos=[Video(filepath=video_path)])

## Multimodal outputs from an agent

Similar to providing multimodal inputs, you can also get multimodal outputs from an agent. You can either use tools to generate image/audio/video or use the agent’s model to generate them (if the model supports this capability).The following example demonstrates how to generate an image using an OpenAI tool with an agent.

image\_agent.py

    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.tools.openai import OpenAITools
    from agno.utils.media import save_base64_data
    
    agent = Agent(
        model=OpenAIChat(id="gpt-5-mini"),
        tools=[OpenAITools(image_model="gpt-image-1")],
        markdown=True,
    )
    
    response = agent.run(
        "Generate a photorealistic image of a cozy coffee shop interior",
    )
    
    if response.images and response.images[0].content:
        save_base64_data(str(response.images[0].content), "tmp/coffee_shop.png")

The output of the tool generating a media also goes to the model’s input as a message so it has access to the media (image, audio, video) and can use it in the response. For example, if you say “Generate an image of a dog and tell me its color.” the model will have access to the image and can use it to describe the dog’s color in the response in the same run.

### Image Model Response

The following example demonstrates how some models can directly generate images as part of their response.

image\_agent.py

    from io import BytesIO
    
    from agno.agent import Agent, RunOutput  # noqa
    from agno.models.google import Gemini
    from PIL import Image
    
    # No system message should be provided
    agent = Agent(
        model=Gemini(
            id="gemini-2.0-flash-exp-image-generation",
            response_modalities=["Text", "Image"], # This means to generate both images and text
        )
    )
    
    # Print the response in the terminal
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
    

You can find all generated images in the `RunOutput.images` list.

The following example demonstrates how to generate an audio using the ElevenLabs tool with an agent. See [Eleven Labs]() for more details.

audio\_agent.py

    import base64
    
    from agno.agent import Agent
    from agno.models.google import Gemini
    from agno.tools.eleven_labs import ElevenLabsTools
    from agno.utils.media import save_base64_data
    
    audio_agent = Agent(
        model=Gemini(id="gemini-2.5-pro"),
        tools=[
            ElevenLabsTools(
                voice_id="21m00Tcm4TlvDq8ikWAM",
                model_id="eleven_multilingual_v2",
                target_directory="audio_generations",
            )
        ],
        description="You are an AI agent that can generate audio using the ElevenLabs API.",
        instructions=[
            "When the user asks you to generate audio, use the `generate_audio` tool to generate the audio.",
            "You\"ll generate the appropriate prompt to send to the tool to generate audio.",
            "You don\"t need to find the appropriate voice first, I already specified the voice to user."
            "Return the audio file name in your response. Don\"t convert it to markdown.",
            "The audio should be long and detailed.",
        ],
        markdown=True,
    )
    
    response = audio_agent.run(
        "Generate a very long audio of history of french revolution and tell me which subject it belongs to.",
        debug_mode=True,
    )
    
    if response.audio:
        print("Agent response:", response.content)
        base64_audio = base64.b64encode(response.audio[0].content).decode("utf-8")
        save_base64_data(base64_audio, "tmp/french_revolution.mp3")
        print("Successfully saved generated speech to tmp/french_revolution.mp3")
    
    
    audio_agent.print_response("Generate a kick sound effect")
    

### Audio Model Response

The following example demonstrates how some models can directly generate audio as part of their response.

audio\_agent.py

    from agno.agent import Agent, RunOutput
    from agno.models.openai import OpenAIChat
    from agno.utils.audio import write_audio_to_file
    
    agent = Agent(
        model=OpenAIChat(
            id="gpt-5-mini-audio-preview",
            modalities=["text", "audio"],
            audio={"voice": "alloy", "format": "wav"},
        ),
        markdown=True,
    )
    response: RunOutput = agent.run("Tell me a 5 second scary story")
    
    # Save the response audio to a file
    if response.response_audio is not None:
        write_audio_to_file(
            audio=agent.run_response.response_audio.content, filename="tmp/scary_story.wav"
        )
    

The following example demonstrates how to generate a video using `FalTools` with an agent. See [FAL]() for more details.

video\_agent.py

    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.tools.fal import FalTools
    
    fal_agent = Agent(
        name="Fal Video Generator Agent",
        model=OpenAIChat(id="gpt-5-mini"),
        tools=[
            FalTools(
                model="fal-ai/hunyuan-video",
                enable_generate_media=True,
            )
        ],
        description="You are an AI agent that can generate videos using the Fal API.",
        instructions=[
            "When the user asks you to create a video, use the `generate_media` tool to create the video.",
            "Return the URL as raw to the user.",
            "Don\"t convert video URL to markdown or anything else.",
        ],
        markdown=True,
    )
    
    fal_agent.print_response("Generate video of balloon in the ocean")
    
    

## Multimodal inputs and outputs together

You can create agents that can take multimodal inputs and return multimodal outputs. The following example demonstrates how to provide a combination of audio and text inputs to an agent and obtain both text and audio outputs.

### Audio input and Audio output

audio\_agent.py

    import requests
    from agno.agent import Agent
    from agno.media import Audio
    from agno.models.openai import OpenAIChat
    from agno.utils.audio import write_audio_to_file
    from rich.pretty import pprint
    
    # Fetch the audio file and convert it to a base64 encoded string
    url = "https://openaiassets.blob.core.windows.net/$web/API/docs/audio/alloy.wav"
    response = requests.get(url)
    response.raise_for_status()
    wav_data = response.content
    
    agent = Agent(
        model=OpenAIChat(
            id="gpt-5-mini-audio-preview",
            modalities=["text", "audio"],
            audio={"voice": "sage", "format": "wav"},
        ),
        markdown=True,
    )
    
    run_response = agent.run(
        "What\"s in these recording?",
        audio=[Audio(content=wav_data, format="wav")],
    )
    
    if run_response.response_audio is not None:
        pprint(run_response.content)
        write_audio_to_file(
            audio=run_response.response_audio.content, filename="tmp/result.wav"
        )

## Developer Resources

*   View more [Examples]()
*   View [Cookbook]()

Was this page helpful?

YesNo






# Tools Introduction




# What are Tools?

Search...

Ctrl K

Tools are what make Agents capable of real-world action. While using LLMs directly you can only generate text, Agents equipped with tools can They are used to enable Agents to interact with external systems, and perform actions like searching the web, running SQL, sending an email or calling APIs. Agno comes with 120+ pre-built toolkits, which you can use to give your Agents all kind of abilities. You can also write your own tools, to give your Agents even more capabilities. The general syntax is:

    import random
    
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.tools import tool
    
    # This is our tool, marked by the @tool decorator
    @tool(stop_after_tool_call=True)
    def get_weather(city: str) -> str:
        """Get the weather for the given city."""
    
        # In a real implementation, this would call a weather API
        weather_conditions = ["sunny", "cloudy", "rainy", "snowy", "windy"]
        random_weather = random.choice(weather_conditions)
    
        return f"The weather in {city} is {random_weather}."
    
    # To equipt our Agent with our tool, we simply pass it with the tools parameter
    agent = Agent(
        model=OpenAIChat(id="gpt-5-nano"),
        tools=[get_weather],
        markdown=True,
    )
    
    # Our Agent will now be able to use our tool, when it deems it relevant
    agent.print_response("What is the weather in San Francisco?", stream=True)
    

In the example above, the `get_weather` function is a tool. When called, the tool result is shown in the output.Then, the Agent will stop after the tool call (without waiting for the model to respond) because we set `stop_after_tool_call=True`.

The `Toolkit` class provides a way to manage multiple tools with additional control over their execution. You can specify which tools should stop the agent after execution and which should have their results shown.

    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    
    # Importing our GoogleSearchTools ToolKit, containing multiple web search tools
    from agno.tools.googlesearch import GoogleSearchTools
    
    agent = Agent(
        model=OpenAIChat(id="gpt-5-mini"),
        tools=[
            GoogleSearchTools(),
        ],
    )
    
    agent.print_response("What\"s the latest about OpenAIs GPT-5?", markdown=True)
    

In this example, the `GoogleSearchTools` toolkit is added to the agent. This ToolKit comes pre-configured with the `google_search` function.Agno automatically provides special parameters to your tools that give access to the agent’s state. These parameters are injected automatically - you don’t pass them when calling the tool.

### Session State Parameter

The built-in parameter `session_state` allows tools to access and modify persistent data across conversations. This is useful in cases where a tool result is relevant for the next steps of the conversation. Add `session_state` as a parameter in your tool function to access the agent’s persistent state:

    from agno.agent import Agent
    from agno.db.sqlite import SqliteDb
    from agno.models.openai import OpenAIChat
    
    
    def add_item(session_state, item: str) -> str:
        """Add an item to the shopping list."""
        session_state["shopping_list"].append(item)  # type: ignore
        return f"The shopping list is now {session_state["shopping_list"]}"  # type: ignore
    
    
    # Create an Agent that maintains state
    agent = Agent(
        model=OpenAIChat(id="gpt-4o-mini"),
        # Initialize the session state with a counter starting at 0 (this is the default session state for all users)
        session_state={"shopping_list": []},
        db=SqliteDb(db_file="tmp/agents.db"),
        tools=[add_item],
        # You can use variables from the session state in the instructions
        instructions="Current state (shopping list) is: {shopping_list}",
        markdown=True,
    )
    
    # Example usage
    agent.print_response("Add milk, eggs, and bread to the shopping list", stream=True)
    print(f"Final session state: {agent.get_session_state()}")
    

See more in [Agent State]().The built-in parameter `images`, `videos`, `audio`, and `files` allows tools to access and modify the input media to an agent.

Using the `send_media_to_model` parameter, you can control whether the media is sent to the model or not and using `store_media` parameter, you can control whether the media is stored in the `RunOutput` or not.

See the [image input example]() and [file input example]() for an advanced example using media.Tools can return different types of results depending on their complexity and what they need to communicate back to the agent.

### Simple Return Types

Most tools can return simple Python types directly like `str`, `int`, `float`, `dict`, and `list`:

    @tool
    def get_weather(city: str) -> str:
        """Get the weather for a city."""
        return f"The weather in {city} is sunny and 75°F"
    
    @tool
    def calculate_sum(a: int, b: int) -> int:
        """Calculate the sum of two numbers."""
        return a + b
    
    @tool
    def get_user_info(user_id: str) -> dict:
        """Get user information."""
        return {
            "user_id": user_id,
            "name": "John Doe",
            "email": "john@example.com",
            "status": "active"
        }
    
    @tool
    def search_products(query: str) -> list:
        """Search for products."""
        return [
            {"id": 1, "name": "Product A", "price": 29.99},
            {"id": 2, "name": "Product B", "price": 39.99}
        ]
    

### `ToolResult` for Media Content

When your tool needs to return media artifacts (images, videos, audio), you **must** use `ToolResult`:
| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `content` | `str` | Required | Main text content/output from the tool |
| `images` | `Optional[List[Image]]` | `None` | Generated image artifacts |
| `videos` | `Optional[List[Video]]` | `None` | Generated video artifacts |
| `audios` | `Optional[List[Audio]]` | `None` | Generated audio artifacts |

    from agno.tools.function import ToolResult
    from agno.media import Image
    
    @tool
    def generate_image(prompt: str) -> ToolResult:
        """Generate an image from a prompt."""
    
        # Create your image (example)
        image_artifact = Image(
            id="img_123",
            url="https://example.com/generated-image.jpg",
            original_prompt=prompt
        )
    
        return ToolResult(
            content=f"Generated image for: {prompt}",
            images=[image]
        )
    

This would **make generated media available** to the LLM model.

## Useful Links

Was this page helpful?

YesNo




# Image Input for Tools




# Image Input for Tools

Search...

Ctrl K

This example demonstrates how tools can receive and process images automatically through Agno’s joint media access functionality. It shows initial image upload and analysis, DALL-E image generation within the same run, and cross-run media persistence.

## Code

cookbook/agents/multimodal/image\_input\_for\_tool.py

    from typing import Optional, Sequence
    
    from agno.agent import Agent
    from agno.db.postgres import PostgresDb
    from agno.media import Image
    from agno.models.openai import OpenAIChat
    from agno.tools.dalle import DalleTools
    
    
    def analyze_images(images: Optional[Sequence[Image]] = None) -> str:
        """
        Analyze all available images and provide detailed descriptions.
    
        Args:
            images: Images available to the tool (automatically injected)
    
        Returns:
            Analysis of all available images
        """
        if not images:
            return "No images available to analyze."
    
        print(f"--> analyze_images received {len(images)} images")
    
        analysis_results = []
        for i, image in enumerate(images):
            if image.url:
                analysis_results.append(
                    f"Image {i + 1}: URL-based image at {image.url}"
                )
            elif image.content:
                analysis_results.append(
                    f"Image {i + 1}: Content-based image ({len(image.content)} bytes)"
                )
            else:
                analysis_results.append(f"Image {i + 1}: Unknown image format")
    
        return f"Found {len(images)} images:\n" + "\n".join(analysis_results)
    
    
    def count_images(images: Optional[Sequence[Image]] = None) -> str:
        """
        Count the number of available images.
    
        Args:
            images: Images available to the tool (automatically injected)
    
        Returns:
            Count of available images
        """
        if not images:
            return "0 images available"
    
        print(f"--> count_images received {len(images)} images")
        return f"{len(images)} images available"
    
    
    def create_sample_image_content() -> bytes:
        """Create a simple image-like content for demonstration."""
        return b"FAKE_IMAGE_CONTENT_FOR_DEMO"
    
    
    def main():
        # Create an agent with both DALL-E and image analysis functions
        agent = Agent(
            model=OpenAIChat(id="gpt-4o"),
            tools=[DalleTools(), analyze_images, count_images],
            name="Joint Media Test Agent",
            description="An agent that can generate and analyze images using joint media access.",
            debug_mode=True,
            add_history_to_context=True,
            send_media_to_model=False,
            db=PostgresDb(db_url="postgresql+psycopg://ai:ai@localhost:5532/ai"),
        )
    
        print("=== Joint Media Access Test ===\n")
    
        # Test 1: Initial image upload and analysis
        print("1. Testing initial image upload and analysis...")
    
        sample_image = Image(id="test_image_1", content=create_sample_image_content())
    
        response1 = agent.run(
            input="I\"ve uploaded an image. Please count how many images are available and analyze them.",
            images=[sample_image],
        )
    
        print(f"Run 1 Response: {response1.content}")
        print(f"--> Run 1 Images in response: {len(response1.input.images or [])}")
        print("\n" + "=" * 50 + "\n")
    
        # Test 2: DALL-E generation + analysis in same run
        print("2. Testing DALL-E generation and immediate analysis...")
    
        response2 = agent.run(input="Generate an image of a cute cat.")
    
        print(f"Run 2 Response: {response2.content}")
        print(f"--> Run 2 Images in response: {len(response2.images or [])}")
        print("\n" + "=" * 50 + "\n")
    
        # Test 3: Cross-run media persistence
        print("3. Testing cross-run media persistence...")
    
        response3 = agent.run(
            input="Count how many images are available from all previous runs and analyze them."
        )
    
        print(f"Run 3 Response: {response3.content}")
        print("\n" + "=" * 50 + "\n")
    
    
    if __name__ == "__main__":
        main()
    

## Usage

1

Create a virtual environment

Open the `Terminal` and create a python virtual environment.

Mac

Windows

    python3 -m venv .venv
    source .venv/bin/activate
    

2

Set your API key

    export OPENAI_API_KEY=xxx
    

3

Set up PostgreSQL

    # Start PostgreSQL with Docker
    docker run -d \
      --name postgres-ai \
      -e POSTGRES_DB=ai \
      -e POSTGRES_USER=ai \
      -e POSTGRES_PASSWORD=ai \
      -p 5532:5432 \
      postgres:16
    

4

Install libraries

    pip install -U agno openai psycopg
    

5

Run Agent

Mac

Windows

    python cookbook/agents/multimodal/image_input_for_tool.py
    

Was this page helpful?

YesNo

