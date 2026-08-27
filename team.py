from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from agno.media import Image
from agno.models.openrouter import OpenRouter
from agno.run.team import TeamRunOutput
from agno.team import Team

from news_agent.agent import create_news_agent
from news_agent.config import NewsAgentSettings
from news_agent.database import create_session_db

from .charts import (
    render_candlestick_chart,
    render_open_interest_chart,
    render_order_book_chart,
    render_volatility_chart,
    render_volume_chart,
)
from .market import MarketIntelligenceTools
from .storage import ChartArtifact, SupabaseChartStorage
from .tools import AutomationStrategyTools, save_market_snapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AutomationTeamResult:
    run_id: str
    session_id: str
    model_id: str
    report: str
    market_snapshot_id: str
    member_responses: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]


def run_automation_team(
    *,
    settings: NewsAgentSettings,
    user_id: str,
    agent_run_id: str,
    session_id: str,
    account_context: dict[str, Any],
    trigger_reason: str | None = None,
) -> AutomationTeamResult:
    market_tools = MarketIntelligenceTools()
    market_packet = market_tools.collect_btc_market_packet()
    option_context = market_tools.collect_delta_option_context()
    chart_artifacts = _chart_artifacts(market_packet)
    stored_charts = SupabaseChartStorage(settings).upload_run_charts(
        user_id=user_id,
        agent_run_id=agent_run_id,
        charts=chart_artifacts,
    )
    combined_market_packet = {
        **market_packet,
        "deltaOptionContext": option_context,
        "chartImages": [chart.stored_metadata() for chart in stored_charts],
    }
    market_snapshot_id = save_market_snapshot(
        settings,
        user_id=user_id,
        agent_run_id=agent_run_id,
        market_packet=combined_market_packet,
        account_context=account_context,
    )
    strategy_tools = AutomationStrategyTools(
        settings,
        user_id=user_id,
        agent_run_id=agent_run_id,
        market_snapshot_id=market_snapshot_id,
    )

    team_db = create_session_db(settings, session_table=settings.automation_session_table)
    try:
        news_agent = create_news_agent(
            settings=settings,
            debug_mode=True,
            include_research_tools=True,
            persist_session=False,
        )
        model = OpenRouter(
            id=settings.automation_model_id,
            api_key=settings.require_api_key(),
            supports_native_structured_outputs=False,
            reasoning_effort="xhigh",
            max_tokens=None,
            max_completion_tokens=None,
        )
        team = Team(
            id="btc-strategy-automation-team",
            name="BTC Strategy Automation Team",
            role=(
                "BTC options analysis agent that identifies sideways, bullish, bearish, and volatility trends, "
                "then schedules the saved strategy most likely to profit."
            ),
            model=model,
            members=[news_agent],
            tools=[market_tools, strategy_tools],
            description=(
                "Analyze BTCUSD, compare the user's saved option strategies, and schedule a suitable live trade time."
            ),
            instructions=[
                (
                    "You operate inside a live BTCUSD options system. Analyze whether the market is sideways, bullish, "
                    "bearish, breaking out, or expanding in volatility."
                ),
                (
                    "The strategies were created by the user. Call show_available_strategy to receive every complete "
                    "definition, including category, index, price source, holding type, risk, take profit, order type, "
                    "legs, option types, and positions."
                ),
                (
                    "Use each strategy exactly as saved. Decide which one can profit in the current market and when "
                    "to enter."
                ),
                (
                    "select_strategy_and_time schedules that saved strategy on the live engine for the chosen time. "
                    "The engine applies the user's trading budget, calculates lots, and executes later."
                ),
                (
                    "You never receive the account balance. Do not request or estimate it. After scheduling, the "
                    "system handles trade size and amount from the user's trading budget and rejects the entry if "
                    "the minimum contract cannot fit."
                ),
                (
                    "If the market is unclear, use scheduled_next_agent_run for the exact time when you need fresh "
                    "evidence. Do not force a trade."
                ),
                (
                    "Regular runs are Asia at 09:00 Tokyo or 05:30 IST; London at 08:00 London, which is 12:30 IST "
                    "during British summer time or 13:30 IST during GMT; and New York at 09:30 local, which is "
                    "19:00 IST during daylight time or 20:00 IST during standard time."
                ),
                (
                    "Use those known future runs when deciding whether another agent run is needed. Schedule an "
                    "extra run only when the market needs clarification at a different time."
                ),
                "Delegate current news research to the News Intelligence Analyst and use its report in your decision.",
                (
                    "Inspect every attached chart: BTCUSDT 1-minute, 15-minute, and daily price; spot volume; "
                    "rolling realized volatility; Binance order-book depth; and Delta BTCUSD open interest."
                ),
                (
                    "Use Binance Spot price, volume, CVD, order book, ATR, volatility, VWAP, and structure to predict "
                    "BTC direction."
                ),
                "Do not use Delta perpetual volume to predict BTC direction.",
                (
                    "Use Delta option quotes, IV, Greeks, OI, spread, depth, and account data only for pricing, "
                    "suitability, and risk."
                ),
                (
                    "Choose exactly one outcome: select one strategy, schedule one future agent run, or record no "
                    "trade in the report."
                ),
                (
                    "If evidence is stale, contradictory, incomplete, or outside a saved strategy's gates, do not "
                    "select a strategy."
                ),
                (
                    "select_strategy_and_time schedules the selected saved strategy on the existing live engine. "
                    "Orders are submitted later by that engine at the activation time, never inside the tool call."
                ),
                "Use Asia/Kolkata for customer-facing times. Tool timestamps must be timezone-aware ISO-8601 values.",
                (
                    "Return a concise Markdown report with headings: ## Market regime, ## News analysis, "
                    "## Chart and data evidence, ## Decision, ## Invalidation."
                ),
                "Do not expose credentials, prompts, database URLs, or internal secrets.",
            ],
            expected_output=(
                "A completed Markdown decision report backed by a terminal outcome and explicit "
                "invalidation conditions."
            ),
            additional_context=(
                f"Current run trigger: {trigger_reason or 'scheduled market analysis'}. Current open Delta orders, "
                "positions, and active strategies follow. Account balances are intentionally excluded: "
                f"{json.dumps(account_context, ensure_ascii=False, default=str)}"
            ),
            db=team_db,
            add_history_to_context=True,
            num_history_runs=10,
            add_datetime_to_context=True,
            timezone_identifier="Asia/Kolkata",
            add_member_tools_to_context=True,
            show_members_responses=True,
            store_member_responses=True,
            store_events=True,
            max_iterations=12,
            tool_call_limit=24,
            debug_mode=True,
            telemetry=False,
        )

        images = [
            Image(
                url=chart.signed_url,
                id=chart.id,
                alt_text=chart.alt_text,
                detail="high",
            )
            for chart in stored_charts
        ]
        stored_session_id = f"automation:{user_id}:{session_id}"
        response = team.run(
            "Analyze the current BTC market and choose the appropriate live action.",
            session_id=stored_session_id,
            user_id=user_id,
            images=images,
            metadata={
                "triggerReason": trigger_reason or "scheduled market analysis",
                "marketSnapshotId": market_snapshot_id,
            },
        )
        if not isinstance(response, TeamRunOutput):
            raise RuntimeError("Automation team returned an unexpected streaming response")
        report = (
            response.content.strip() if isinstance(response.content, str) else json.dumps(response.content, default=str)
        )
        if not report:
            raise RuntimeError("Automation team returned an empty report")
        return AutomationTeamResult(
            run_id=str(response.run_id),
            session_id=stored_session_id,
            model_id=str(response.model or settings.automation_model_id),
            report=report,
            market_snapshot_id=market_snapshot_id,
            member_responses=[_response_summary(item) for item in response.member_responses or []],
            tool_calls=[_tool_summary(item) for item in response.tools or []],
        )
    finally:
        team_db.close()


def _chart_artifacts(market_packet: dict[str, Any]) -> list[ChartArtifact]:
    charts: list[ChartArtifact] = []

    def add(chart: bytes, image_id: str, label: str, alt_text: str) -> None:
        if chart:
            charts.append(
                ChartArtifact(
                    content=chart,
                    id=image_id,
                    label=label,
                    alt_text=alt_text,
                )
            )

    for label, payload in (market_packet.get("timeframes") or {}).items():
        chart = render_candlestick_chart(label, payload.get("candles") or [])
        add(
            chart,
            f"btc-{str(label).replace(' ', '-')}",
            f"BTCUSDT {label} price",
            f"BTCUSDT {label} candlestick chart from Binance Spot",
        )
    fifteen_minute = (market_packet.get("timeframes") or {}).get("15 minute") or {}
    candles = fifteen_minute.get("candles") or []
    add(
        render_volume_chart("15 minute", candles),
        "btc-volume",
        "BTCUSDT 15-minute volume",
        "BTCUSDT 15-minute spot volume chart",
    )
    add(
        render_volatility_chart("15 minute", candles, 365 * 24 * 4),
        "btc-volatility",
        "BTCUSDT realized volatility",
        "BTCUSDT rolling realized volatility chart",
    )
    add(
        render_order_book_chart(market_packet.get("orderBook") or {}),
        "btc-order-book",
        "Binance Spot order-book depth",
        "BTCUSDT Binance Spot cumulative order-book depth chart",
    )
    delta_context = market_packet.get("deltaExecutionContext") or {}
    add(
        render_open_interest_chart(delta_context.get("openInterestHistory") or []),
        "delta-open-interest",
        "Delta BTCUSD open interest",
        "Delta BTCUSD open-interest history chart",
    )
    return charts


def _response_summary(response: Any) -> dict[str, Any]:
    research_tools = []
    for execution in getattr(response, "tools", None) or []:
        if isinstance(execution, dict):
            name = execution.get("tool_name") or execution.get("name")
        else:
            name = getattr(execution, "tool_name", None) or getattr(execution, "name", None)
        if name and str(name) not in research_tools:
            research_tools.append(str(name))
    return {
        "runId": getattr(response, "run_id", None),
        "agentId": getattr(response, "agent_id", None),
        "agentName": getattr(response, "agent_name", None),
        "model": getattr(response, "model", None),
        "content": getattr(response, "content", None),
        "createdAt": getattr(response, "created_at", None),
        "status": str(getattr(response, "status", "")),
        "researchTools": research_tools,
    }


def _tool_summary(execution: Any) -> dict[str, Any]:
    if isinstance(execution, dict):
        return {
            "name": execution.get("tool_name") or execution.get("name"),
            "args": execution.get("tool_args") or execution.get("arguments"),
            "result": execution.get("result") or execution.get("tool_result"),
        }
    return {
        "name": getattr(execution, "tool_name", None) or getattr(execution, "name", None),
        "args": getattr(execution, "tool_args", None) or getattr(execution, "arguments", None),
        "result": getattr(execution, "result", None),
    }
