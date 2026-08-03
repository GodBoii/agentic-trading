# python-backend/image_tools.py

import logging
import uuid
import base64
import traceback
from typing import Dict, Any

from agno.tools import Toolkit
from agno.agent import Agent
from agno.models.google import Gemini
from agno.media import Image
from agno.run.agent import RunOutput

logger = logging.getLogger(__name__)

class ImageTools(Toolkit):
    """
    A toolkit for generating images using Google's Gemini model.
    It handles the generation internally and emits the result directly
    to the frontend via Socket.IO for immediate display in the artifact viewer.
    """

    def __init__(self, custom_tool_config: Dict[str, Any]):
        """
        Initializes the ImageTools toolkit.

        Args:
            custom_tool_config (Dict[str, Any]): A dictionary containing runtime
                configuration needed for real-time communication, specifically:
                - socketio: The Flask-SocketIO server instance.
                - sid: The Socket.IO session ID of the requesting client.
                - message_id: The unique ID of the current user message/turn.
        """
        # Call the parent Toolkit constructor. The Toolkit will automatically
        # convert the methods listed in `tools` into usable tool objects.
        # The @tool decorator is NOT needed on methods within a Toolkit class.
        super().__init__(
            name="image_tools",
            tools=[self.generate_image],
        )

        # Store the communication configuration for direct event emission.
        self.socketio = custom_tool_config.get('socketio')
        self.sid = custom_tool_config.get('sid')
        self.message_id = custom_tool_config.get('message_id')

        if not all([self.socketio, self.sid, self.message_id]):
            logger.error("ImageTools: Missing config (socketio/sid/message_id)")

    def generate_image(self, prompt: str) -> str:
        """
        Generates an image based on the provided text prompt. The generated image
        is sent directly to the frontend for display, and a markdown reference to
        the image artifact is returned to be included in the chat response.

        Args:
            prompt (str): A detailed description of the image to generate.

        Returns:
            str: A status message containing a markdown reference to the generated image artifact,
                 or an error message if generation fails.
        """
        if not all([self.socketio, self.sid, self.message_id]):
             return "Error: Image generation service is not properly configured. Cannot emit image event."

        try:
            # 1. Instantiate an internal, single-purpose Agent for image generation.
            artist_agent = Agent(
                name="artist_agent",
                model=Gemini(
                    id="gemini-2.0-flash-exp-image-generation",
                    response_modalities=["Text", "Image"],
                ),
                debug_mode=False,
            )

            # 2. Execute the internal agent to generate the image.
            run_output: RunOutput = artist_agent.run(prompt)

            # 3. Validate the output and extract the raw image bytes.
            if not run_output or not run_output.images or not run_output.images[0].content:
                logger.error("Image generation failed: No content")
                return "Error: The image generation model did not return an image for this prompt."

            image_artifact: Image = run_output.images[0]
            image_bytes: bytes = image_artifact.content

            # 4. Prepare the data for frontend consumption.
            artifact_id = f"image-artifact-{uuid.uuid4()}"
            base64_image = base64.b64encode(image_bytes).decode('utf-8')

            # 5. Construct the payload for the real-time event.
            event_payload = {
                "id": self.message_id,
                "artifactId": artifact_id,
                "image_base64": base64_image,
                "agent_name": "ImageTools",
            }

            # 6. Emit the custom Socket.IO event directly to the specific frontend client.
            try:
                # Broadcast to all clients to avoid socket ID mismatch issues
                self.socketio.emit("image_generated", event_payload, broadcast=True)
            except Exception as emit_error:
                logger.error(f"Image emit failed: {emit_error}")

            # 7. Return the markdown reference for the chat history.
            #    This is the "in-band" result that gets processed by the main agent and chat UI.
            return f"I have generated an image for you.\n\n```image\n{artifact_id}\n```"

        except Exception as e:
            # Catch any unexpected errors, log them for debugging, and return a user-friendly message.
            error_msg = f"Error during image generation tool execution: {str(e)}"
            logger.error(f"ImageTools: {error_msg}\n{traceback.format_exc()}")
            return f"An unexpected error occurred while trying to generate the image. Please check the logs."