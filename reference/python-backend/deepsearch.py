from agno.agent import Agent, AgentMemory
from agno.models.google import Gemini
from agno.models.groq import Groq
from agno.storage.json import JsonStorage
from agno.memory.db.sqlite import SqliteMemoryDb
from agno.memory.classifier import MemoryClassifier
from agno.memory.summarizer import MemorySummarizer
from agno.team.team import Team
from agno.tools.googlesearch import GoogleSearchTools
from agno.tools.shell import ShellTools
from agno.tools.calculator import CalculatorTools
from agno.tools.crawl4ai import Crawl4aiTools
from agno.tools.python import PythonTools
from agno.media import Image, Audio, Video
from typing import List, Optional, Dict, Any, Union
import base64
import requests

def get_deepsearch(
    ddg_search: bool = False,
    web_crawler: bool = False,
    investment_assistant: bool = False,
    calculator: bool = False,
    shell_tools: bool = False,
    python_assistant: bool = False,
    use_memory: bool = False,
    use_session_summaries: bool = False,
    user_id: Optional[str] = None,
    run_id: Optional[str] = None,
    debug_mode: bool = True,
) -> Union[Agent, 'DeepSearch']:
    """
    Create and return a DeepSearch agent based on agno framework.
    This provides an equivalent functionality to get_llm_os in assistant.py
    but uses the agno framework instead of phidata.
    
    Returns either an Agent object directly or a DeepSearch wrapper,
    based on how it's called.
    """
    tools = []
    instructions = [
        "Your primary responsibility is to assist the user effectively and efficiently.",
        "Analyze the user's message and the conversation history to understand their intent and context.",
        "Prioritize using available tools to answer the user's query.",
        "Provide clear, concise, and informative answers."
    ]

    # Configure memory
    if use_memory:
        memory = AgentMemory(
            classifier=MemoryClassifier(model=Gemini(id="gemini-2.0-flash")),
            summarizer=MemorySummarizer(model=Gemini(id="gemini-2.0-flash")),
            db=SqliteMemoryDb(table_name="ai_os_agent_memory", db_file="storage/tmp/aios_memory.db"),
            create_user_memories=True,
            create_session_summary=use_session_summaries
        )
        instructions.append("Use the `search_knowledge_base` tool to search your memory for relevant information.")
    else:
        memory = None

    # Add calculator tools if requested
    if calculator:
        tools.append(CalculatorTools(
            add=True,
            subtract=True,
            multiply=True,
            divide=True,
            exponentiate=True,
            factorial=True,
            is_prime=True,
            square_root=True,
        ))
        instructions.append("Use the Calculator tool for mathematical operations.")

    # Add DuckDuckGo search if requested
    if ddg_search:
        tools.append(GoogleSearchTools())
        instructions.append("Use DuckDuckGoTools for web / internet searches. Always include sources.")

    # Add shell tools if requested
    if shell_tools:
        tools.append(ShellTools())
        instructions.append("Use shell commands to fulfill user requests when needed.")

    # Create team of sub-agents
    team = []

    if python_assistant:
        python = Agent(
            name="Python Assistant",
            model=Gemini(id="gemini-2.0-flash"),
            tools=[PythonTools()],
            role="Python agent",
            instructions=["you can write and run python code to fulfill users request"],
            show_tool_calls=True,
            debug_mode=debug_mode,
        )
        team.append(python)
        instructions.append("To write and run python code, delegate the task to the `Python Assistant`.")

    if web_crawler:
        crawler = Agent(
            name="Crawler",
            model=Gemini(id="gemini-2.0-flash"),
            description="for the given url crawl the page and extract the text",
            tools=[Crawl4aiTools(max_length=None)],
            show_tool_calls=True,
            debug_mode=debug_mode
        )
        team.append(crawler)
        instructions.append("To extract information from a URL, delegate the task to the `Crawler`.")

    # Create the main AI_OS agent
    AI_OS = Agent(
        name="DeepSearch",
        tools=tools,
        instructions=instructions + [
            "**File Handling:**",
            "   - When images, PDFs, word documents, audio, or video files are provided, analyze their content directly.",
            "   - For images, describe what you see in detail.",
            "   - For PDF and document files, summarize the content and answer questions about it.",
            "   - For audio files, describe what you hear.",
            "   - For video files, describe the scenes and content."
        ],
        description=["You are DeepSearch, an advanced AI agent from AI-OS. Your purpose is to provide users with comprehensive and insightful answers by deeply researching their questions and leveraging available tools and specialized AI assistants. You prioritize accuracy, thoroughness, and actionable information.",
                     "Your primary goal is to deeply understand the user's needs and provide comprehensive and well-researched answers.",

                    "**First, analyze the user's message and the conversation history to understand their intent and context.** Pay close attention to any specific requests, topics of interest, or information provided by the user.",
                    
                    "**When files, images, audio, or video are provided, analyze them carefully and include their content in your response.**",

                    "**Employ a systematic approach to answer the user's query, prioritizing thoroughness and accuracy.**",

                    "**Decision-Making Process (in order of priority):**",
                    "1. **Clarification:** If the user's question is unclear or requires further information, ask clarifying questions. Avoid making assumptions.",
                    "2. **Knowledge Base Search:** ALWAYS begin by searching your knowledge base using `search_knowledge_base` to identify any relevant existing information. Summarize relevant findings from your knowledge base.",
                    "3. **Internet Search:** If the knowledge base doesn't contain a sufficient answer, use `duckduckgo_search` to conduct a thorough internet search.  Consolidate findings from multiple reputable sources and **always cite your sources with URLs.**",
                    "4. **Tool Delegation:** If a specific tool is required to fulfill the user's request (e.g., performing calculations), use the appropriate tool immediately.",
                    "5. **Assistant Delegation:** If a task is best handled by a specialized AI Assistant (e.g., creating an investment report, extracting information from a URL), delegate the task to the appropriate assistant and synthesize their response for the user.",
                    "6. **Synthesis and Reporting:**  Compile the information gathered from all sources (knowledge base, internet search, tools, and assistants) into a coherent and comprehensive answer for the user.  Organize your response logically and provide sufficient context and detail.",

                    "**Tool Usage Guidelines:**",
                    "   - For mathematical calculations, use the `Calculator` tool if precision is required.",
                    "   - For up-to-date information, use the `DuckDuckGo` tool.  **Always include the source URLs.**",
                    "   - When the user provides a URL, IMMEDIATELY use the `Web Crawler` tool without any preliminary message.",
                    "   - Delegate investment report requests to the `Investment Assistant`.",

                    "**Response Guidelines:**",
                    "   - Provide clear, concise, and informative answers.  Avoid ambiguity and jargon.",
                    "   - Explain your reasoning and the steps you took to arrive at your answer.  This demonstrates transparency and helps the user understand your process.",
                    "   - If you delegate a task to an AI Assistant, summarize their response and integrate it into your overall answer.  Provide additional context and analysis as needed.",
                    "   - Tailor your response to the user's level of understanding.  Provide more detail for complex topics or for users who are unfamiliar with the subject matter.",
                    "   - Consider potential follow-up questions the user might have and proactively address them in your response.",

                    "**Memory Usage:**",
                    "   - Use the `get_chat_history` tool if the user explicitly asks you to summarize or reference your conversation.",

                    "**Important Notes:**",
                    "   - You have access to long-term memory. Use the `search_knowledge_base` tool to search your memory for relevant information.",
                    "   - Focus on providing detailed and insightful answers. Do not simply provide a surface-level response. Dig deep and explore all relevant aspects of the user's question.",
                    "   - Think critically and evaluate the information you gather from different sources. Do not simply repeat information without considering its validity and reliability.",
                    ],
        team=team,
        model=Gemini(id="gemini-2.0-flash"),
        reasoning=False,
        markdown=True,
        storage=JsonStorage(dir_path="storage/tmp/deepsearch_agent_sessions.json"),
        memory=memory,
        add_history_to_messages=True,
        num_history_responses=6,
        debug_mode=debug_mode,
        show_tool_calls=True,
        add_datetime_to_instructions=True,
    )
    
    # Return either the Agent directly or wrap it in DeepSearch
    # This allows for backward compatibility
    return DeepSearch(config={
        "ddg_search": ddg_search,
        "web_crawler": web_crawler,
        "investment_assistant": investment_assistant,
        "calculator": calculator,
        "shell_tools": shell_tools,
        "python_assistant": python_assistant,
        "use_memory": use_memory,
        "use_session_summaries": use_session_summaries,
    }, agent=AI_OS, debug_mode=debug_mode)

class DeepSearch:
    """
    A class to handle agno agent interactions similar to how
    assistant.py handles phidata agents.
    """
    
    def __init__(self, config: Dict[str, bool] = None, agent: Agent = None, debug_mode: bool = True):
        """
        Initialize the DeepSearch agent with the given configuration.
        
        Args:
            config: Configuration dictionary for the agent
            agent: Pre-configured agent (if provided, config is ignored)
            debug_mode: Whether to enable debug mode
        """
        if config is None:
            config = {}
            
        self.debug_mode = debug_mode
        
        if agent:
            self.agent = agent
        else:
            # Create a new agent using the configuration
            self.agent = self._create_agent(config)
    
    def _create_agent(self, config: Dict[str, bool]) -> Agent:
        """Create an agent with the given configuration."""
        return get_deepsearch(
            ddg_search=config.get("ddg_search", False),
            web_crawler=config.get("web_crawler", False),
            investment_assistant=config.get("investment_assistant", False),
            calculator=config.get("calculator", False),
            shell_tools=config.get("shell_tools", False),
            python_assistant=config.get("python_assistant", False),
            use_memory=config.get("use_memory", False),
            use_session_summaries=config.get("use_session_summaries", False),
            debug_mode=self.debug_mode
        )
        
    def run(self, message: str, context: str = None, stream: bool = False, 
            images: List[Dict] = None, audio_data: List[Dict] = None, 
            video_data: List[Dict] = None):
        """
        Run the agent with the given message and return the response.
        
        Args:
            message: The message to send to the agent
            context: Additional context to include with the message
            stream: Whether to stream the response
            images: List of dictionaries with image data (optional)
            audio_data: List of dictionaries with audio data (optional)
            video_data: List of dictionaries with video data (optional)
            
        Returns:
            The agent's response or a stream of responses
        """
        # Process inputs for multimodal capabilities
        agno_images = None
        agno_audio = None
        agno_videos = None
        
        # Process images if provided
        if images and len(images) > 0:
            agno_images = []
            for img in images:
                if img and 'url' in img and img['url']:
                    agno_images.append(Image(url=img['url']))
                elif img and 'base64' in img and img['base64']:
                    agno_images.append(Image(base64=img['base64']))
                elif img and 'filepath' in img and img['filepath']:
                    agno_images.append(Image(filepath=img['filepath']))
        
        # Process audio if provided
        if audio_data and len(audio_data) > 0:
            agno_audio = []
            for audio in audio_data:
                if audio and 'content' in audio and audio['content']:
                    agno_audio.append(Audio(content=audio['content'], format=audio.get('format', 'wav')))
                elif audio and 'filepath' in audio and audio['filepath']:
                    agno_audio.append(Audio(filepath=audio['filepath']))
        
        # Process video if provided
        if video_data and len(video_data) > 0:
            agno_videos = []
            for video in video_data:
                if video and 'filepath' in video and video['filepath']:
                    agno_videos.append(Video(filepath=video['filepath']))
        
        # Combine context with message if provided
        if context:
            complete_message = f"Previous conversation context:\n{context}\n\nCurrent message: {message}"
        else:
            complete_message = message

        # Run the agent with the appropriate inputs
        return self.agent.run(
            complete_message, 
            stream=stream,
            images=agno_images,  # Only pass if not None
            audio=agno_audio,    # Only pass if not None
            videos=agno_videos   # Only pass if not None
        )
    
    def print_response(self, message, images=None, audio=None, videos=None, stream=False):
        """
        Print the agent's response to the console.
        This is a convenience method for testing the agent.
        """
        kwargs = {'stream': stream}
        
        if images:
            kwargs['images'] = images
        if audio:
            kwargs['audio'] = audio
        if videos:
            kwargs['videos'] = videos
            
        return self.agent.print_response(message, **kwargs)

