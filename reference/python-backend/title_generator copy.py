
import logging
from agno.agent import Agent
from agno.models.google import Gemini
from agno.models.groq import Groq
from supabase_client import supabase_client
import uuid

logger = logging.getLogger(__name__)

def generate_and_save_title(conversation_id: str, user_id: str, first_message: str, session_created_at: int = None):
    """
    Generates a 3-4 word title for a conversation based on the first message
    and saves it to the session_titles table in Supabase.
    """
    try:
        # Basic validation
        if not first_message or not first_message.strip():
            logger.warning(f"Empty first message for session {conversation_id}, skipping title generation.")
            return

        # Ensure conversation_id is a valid UUID if the table requires it
        try:
            uuid_obj = uuid.UUID(conversation_id)
            session_uuid = str(uuid_obj)
        except ValueError:
            logger.error(f"conversation_id {conversation_id} is not a valid UUID. Cannot save to session_titles.")
            return

        logger.info(f"Generating title for session {conversation_id} based on message: {first_message[:50]}...")

        # Initialize a lightweight agent for this specific task
        # Using gemini-2.0-flash-exp as it is generally faster/cheaper, or fallback to what is used in the project
        agent = Agent(
            model=Groq(id="openai/gpt-oss-20b"), 
            instructions=(
                "You are a helpful assistant that generates a short, concise title (max 4 words) "
                "for a conversation based on the user's first message. "
                "Do NOT use quotes. Just return the clear text title."
            ),
            markdown=False,
        )

        # Run the agent
        response = agent.run(first_message)
        
        if not response or not response.content:
            logger.warning(f"Agent returned empty response for title generation (session {conversation_id})")
            return

        title = response.content.strip()
        # Remove any surrounding quotes just in case
        title = title.replace('"', '').replace("'", "")
        
        logger.info(f"Generated title: '{title}' for session {conversation_id}")

        # Prepare data for Supabase
        # Table schema: session_id (uuid), user_id (uuid), tittle (text), created_at...
        data = {
            "session_id": session_uuid,
            "user_id": user_id,
            "tittle": title,  # Note: using 'tittle' as per the schema
            "session_created_at": session_created_at
        }
        
        # Insert into Supabase
        result = supabase_client.from_("session_titles").insert(data).execute()
        logger.info(f"Successfully saved title for session {conversation_id}")

    except Exception as e:
        logger.error(f"Error in generate_and_save_title for session {conversation_id}: {e}")
