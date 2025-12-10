# python-backend/assistant.py (Final, Corrected Version for Agno v2.0.7 - Path B)

import os
import base64
import traceback
import logging
import uuid
from typing import Optional, List, Dict, Any, Union

# Agno Core Imports
from agno.agent import Agent
from agno.team import Team  # <-- Use the standard Team class
from agno.media import Image
from agno.tools import tool

# V2 Imports
from agno.run.team import TeamRunEvent
from agno.run.agent import RunEvent
from agno.db.postgres import PostgresDb
from agno.models.google import Gemini
from agno.models.groq import Groq

# Tool Imports
from agno.tools import Toolkit
from agno.tools.googlesearch import GoogleSearchTools
from agno.models.openrouter import OpenRouter

# Other Imports
from supabase_client import supabase_client

logger = logging.getLogger(__name__)


def get_llm_os(
    user_id: Optional[str] = None,
    session_info: Optional[Dict[str, Any]] = None,
    internet_search: bool = False,
    coding_assistant: bool = False,
    World_Agent: bool = False,
    Planner_Agent: bool = False,
    use_memory: bool = False,
    debug_mode: bool = True,
    custom_tool_config: Optional[Dict[str, Any]] = None,
) -> Team:
    """
    Constructs the hierarchical Aetheria AI multi-agent system with integrated planner.
    """
    direct_tools: List[Union[Toolkit, callable]] = []

    db_url_full = os.getenv("DATABASE_URL")
    if not db_url_full:
        raise ValueError("DATABASE_URL environment variable is not set.")
    db_url_sqlalchemy = db_url_full.replace("postgresql://", "postgresql+psycopg2://")

    # This PostgresDb object is now the single source of truth for persistence.
    # The Team will use it automatically to save runs and memories to Supabase.
    db = PostgresDb(
        db_url=db_url_sqlalchemy,
        db_schema="public"
    )

    if internet_search:
        direct_tools.append(GoogleSearchTools(fixed_max_results=15))

    main_team_members: List[Union[Agent, Team]] = []

    # TIER 1: Analysis Agents (Parallel Execution)
    chronos_agent = Agent(
        name="CHRONOS",
        role="Historical Data Analysis Agent - Historical pattern recognition, support/resistance identification, volume profile analysis, statistical properties",
        model=OpenRouter(id="x-ai/grok-4.1-fast:free"),
        tools=[],
        instructions=[],
        markdown=True,
        debug_mode=debug_mode,
    )

    athena_agent = Agent(
        name="ATHENA",
        role="Technical Analysis Agent - Multi-timeframe technical indicators, trend and momentum analysis, chart pattern recognition, indicator confluence detection",
        model=OpenRouter(id="x-ai/grok-4.1-fast:free"),
        tools=[],
        instructions=[],
        markdown=True,
        debug_mode=debug_mode,
    )

    quant_agent = Agent(
        name="QUANT",
        role="Quantitative Analysis Agent - Statistical arbitrage calculations, factor modeling, machine learning predictions, risk metrics computation",
        model=OpenRouter(id="x-ai/grok-4.1-fast:free"),
        tools=[],
        instructions=[],
        markdown=True,
        debug_mode=debug_mode,
    )

    apollo_agent = Agent(
        name="APOLLO",
        role="Fundamental Analysis Agent - Valuation metrics, corporate actions screening, financial health check, earnings calendar monitoring",
        model=OpenRouter(id="x-ai/grok-4.1-fast:free"),
        tools=[],
        instructions=[],
        markdown=True,
        debug_mode=debug_mode,
    )

    hermes_agent = Agent(
        name="HERMES",
        role="News & Sentiment Analysis Agent - Real-time news aggregation, sentiment scoring, event detection, social media analysis",
        model=OpenRouter(id="x-ai/grok-4.1-fast:free"),
        tools=[],
        instructions=[],
        markdown=True,
        debug_mode=debug_mode,
    )

    strategist_agent = Agent(
        name="STRATEGIST",
        role="Strategy & Pattern Selector Agent - Market regime identification, strategy selection from library, indicator combination optimization, pattern recognition and matching",
        model=OpenRouter(id="x-ai/grok-4.1-fast:free"),
        tools=[],
        instructions=[],
        markdown=True,
        debug_mode=debug_mode,
    )

    depth_agent = Agent(
        name="DEPTH",
        role="Order Flow & Microstructure Agent - Level 2 market depth analysis, footprint/cluster chart analysis, cumulative delta calculation, liquidity and order book imbalance, time & sales analysis",
        model=OpenRouter(id="x-ai/grok-4.1-fast:free"),
        tools=[],
        instructions=[],
        markdown=True,
        debug_mode=debug_mode,
    )

    # Create Analysis Team with all TIER 1 agents
    analysis_team = Team(
        name="Analysis_Team",
        model=OpenRouter(id="x-ai/grok-4.1-fast:free"),
        members=[chronos_agent, athena_agent, quant_agent, apollo_agent, hermes_agent, strategist_agent, depth_agent],
        tools=[],
        instructions=[
            "Collaborate to provide comprehensive market analysis.",
            "Each agent contributes their specialized expertise.",
            "Synthesize findings into cohesive trading insights."
        ],
        add_datetime_to_context=True,
        debug_mode=debug_mode,
    )
    main_team_members.append(analysis_team)

    aetheria_instructions = [
        "Provide direct, clear answers without explaining internal processes.",
        "Focus on user value, not system operations.",
        "Keep responses natural and conversational.",
        "Always provide a final answer."
    ]

    # --- CRITICAL CHANGE: Instantiate the standard Team class ---
    # This allows the `db` object to automatically handle session persistence.
    llm_os_team = Team(
        name="Aetheria_AI_Trader",
        model=Gemini(id="gemini-2.5-flash"),
        members=main_team_members,
        tools=direct_tools,
        instructions=aetheria_instructions,
        user_id=user_id,
        db=db,  # This now controls persistence
        enable_agentic_memory=use_memory,
        enable_user_memories=use_memory,
        enable_session_summaries=use_memory,
        stream_intermediate_steps=True,
        search_knowledge=use_memory,
        events_to_skip=[
            TeamRunEvent.run_started,
            TeamRunEvent.run_completed,
            TeamRunEvent.memory_update_started,
            TeamRunEvent.memory_update_completed,
        ],
        read_team_history=True,
        add_history_to_context=True,
        num_history_runs=40,
        store_events=True, # This is crucial for saving the full history
        markdown=True,
        add_datetime_to_context=True,
        debug_mode=debug_mode,
    )

    return llm_os_team