# Agno v2.0 Changelog

Search...

Ctrl K

 This is a major release that introduces a completely new approach to building multi-agent systems. It also introduces the AgentOS, a runtime for agents. This is a major rewrite of the Agno library and introduces various new concepts and updates to the existing ones. Some of the major changes are:

*   Agents, Teams and Workflows are now fully stateless.
*   Knowledge is now a single solution that supports many forms of content.
*   Storage of sessions, memories, evals, etc. has been simplified

## General Changes

Repo Updates

*   `/libs/agno` has been restructured to fit the new concepts in Agno and for better organization.
*   All code related to managing workspaces and agent deployment in Agno has been moved to a new package called `agno-infra`. This is a combination of the previous `agno-aws` and `agno-docker` packages, as well as the CLI and other tools.
*   `agno-aws` and `agno-docker` packages have been deprecated and will no-longer be maintained.
*   All code related to the Agno CLI (`ag`) has been moved to this new `agno-infra` package.
*   Added `AgentOS` to `agno` as a comprehensive API solution for building multi-agent systems. This also replaces `Playground` and other Apps. See details below.
*   Introducing `AgentOS`, a system for hosting agents, teams and workflows as a production-ready API. See full details in the [AgentOS]() section.
*   This adds routes for session management, memory management, knowledge management, evals management, and metrics.
*   This enables you to host agents, teams and workflows, and use the [Agent OS UI]() to manage them.

Apps Deprecations

*   Removed `Playground`. Its functionality has been replaced by `AgentOS`.
*   Removed `AGUIApp` and replace with `AGUI` interface on `AgentOS`.
*   Removed `SlackApi` and replace with `Slack` interface on `AgentOS`.
*   Removed `WhatsappApi` and replace with `Whatsapp` interface on `AgentOS`.
*   Removed `FastAPIApp`. Its functionality has been replaced by `AgentOS`.
*   `DiscordClient` has been moved to `/integrations/discord`.

## Session & Run State

*   We have made significant changes to the innerworkings of `Agent`, `Team` and `Workflow` to make them completely stateless.
*   This means that `agent_session`, `session_metrics`, `session_state`, etc. should not be seen as stateful variables that would be updated during the course of a run, but rather as “defaults” for the agent if they can be set on initialisation.
*   `CustomEvent` is now supported and you can inherit from it to create your own custom events that can be yielded from your own tools. See the [documentation]() for more details.

Updates to Run Objects

For agents:

*   `RunResponse` -> `RunOutput`
*   `RunResponseStartedEvent` -> `RunStartedEvent`
*   `RunResponseContentEvent` -> `RunContentEvent`
*   `RunResponseCompletedEvent` -> `RunCompletedEvent`
*   `IntermediateRunResponseContentEvent` -> `IntermediateRunContentEvent`
*   `RunResponseErrorEvent` -> `RunErrorEvent`
*   `RunResponseCancelledEvent` -> `RunCancelledEvent`

For teams:

*   `TeamRunResponse` -> `TeamRunOutput`
*   `RunResponseStartedEvent` -> `RunStartedEvent`
*   `RunResponseContentEvent` -> `RunContentEvent`
*   `RunResponseCompletedEvent` -> `RunCompletedEvent`
*   `IntermediateRunResponseContentEvent` -> `IntermediateRunContentEvent`
*   `RunResponseErrorEvent` -> `RunErrorEvent`
*   `RunResponseCancelledEvent` -> `RunCancelledEvent`

For workflows:

*   `WorkflowRunResponse` -> `WorkflowRunOutput`
*   `WorkflowRunResponseStartedEvent` -> `WorkflowRunStartedEvent`
*   `WorkflowRunResponseContentEvent` -> `WorkflowRunContentEvent`
*   `WorkflowRunResponseCompletedEvent` -> `WorkflowRunCompletedEvent`
*   `WorkflowRunResponseErrorEvent` -> `WorkflowRunErrorEvent`
*   `WorkflowRunResponseCancelledEvent` -> `WorkflowRunCancelledEvent`
*   The import location for `RunOutput` (and events) has been moved to `agno.run.agent`.
*   For `RunOutput`, `TeamRunOutput` and `WorkflowRunOutput` the `extra_data` attribute has been removed and the internal attributes are now top-level. This is `references`, `additional_input`, `reasoning_steps`, and `reasoning_messages`.
*   `metadata` added to `RunOutput`, `TeamRunOutput` and `WorkflowRunOutput`. This represents all the set metadata for the run.

Updates to Session Objects

*   Session storage now stores `AgentSession`, `TeamSession` and `WorkflowSession` with new schemas. See full details in the [Session]() section.
*   Session objects now have `runs` directly on it.
*   Session objects support new convenience methods:
    *   `get_run` -> Get a specific run by ID.
    *   `get_session_summary` -> Get the session summary.
    *   `get_chat_history` -> Get an aggregated view of all messages for all runs in the session.

Updates to Metrics

*   `SessionMetrics` and `MessageMetrics` have been unified as a single `Metrics` class.
*   `audio_tokens` has been renamed to `audio_total_tokens`.
*   `input_audio_tokens` has been renamed to `audio_input_tokens`.
*   `output_audio_tokens` has been renamed to `audio_output_tokens`.
*   `cached_tokens` has been renamed to `cache_read_tokens`.
*   `prompt_tokens` and `completion_tokens` have been removed (only `input_tokens` and `output_tokens` should be used)
*   `prompt_tokens_details` and `completion_tokens_details` have been removed. Instead `provider_metrics` captures any provider-specific metrics.
*   `time` has been renamed to `duration`.

Cancelling Runs

*   You can now cancel a run by calling `cancel_run` on the `Agent`, `Team` or `Workflow`.
*   This will cancel the run and return a `RunCancelledEvent` during streaming, or set the `RunOutput.status` to `"cancelled"`.

## Storage

*   `Agent`, `Team`, `Workflow` and the various evals now all support a single `db` parameter. This is to enable storage for the instance of that class. This is required for persistence of sessions, memories, metrics, etc.
*   `storage` and `memory` have been removed from `Agent`, `Team` and `Workflow`.

Updates to Storage Classes

*   This means all previous storage providers have been reworked. Also session storage, memory storage and eval storage are all a single solution now referred to as a “DB”.
*   `PostgresStorage` -> `PostgresDb`
*   `SqliteStorage` -> `SqliteDb`
*   `MysqlStorage` -> `MysqlDb`
*   `RedisStorage` -> `RedisDb`
*   `MongoStorage` -> `MongoDb`
*   `DynamoDBStorage` -> `DynamoDb`
*   `SingleStoreStorage` -> `SingleStoreDb`
*   `InMemoryStorage` -> `InMemoryDb`
*   `JsonStorage` -> `JsonDb`
*   `GCSJsonStorage` -> `GCSJsonDb`

## Memory

*   With the above changes to storage, memory has been simplified.
*   `memory` has been removed from `Agent` and `Team`. Instead memory is enabled with `enable_user_memories: bool` (like before) and persisted in the `db` instance.
*   Changes to how memories are created can still be done by overriding the `MemoryManager` class on `Agent` or `Team`. E.g. `Agent(memory_manager=MyMemoryManager())`.
*   `AgentMemory` and `TeamMemory` have been removed.

## Knowledge

*   Knowledge has been completely reworked. See full details in the [Knowledge]() section.
*   You now define a single `Knowledge` instance for all types of content. Files (PDF, CSV, etc.), URLs, and other.
*   The agent can still use your knowledge base to search for information at runtime. All existing RAG implementations are still supported.
*   Added **full `async` support** for embedding models and vector DBs. This has a significant impact on performance and is a major speed improvement when adding content to the knowledge base using `knowledge.add_content_async(...)`.
*   `AgentKnowledge` and all other knowledge base classes have been removed.
*   Import locations for `embedder`, `document`, `chunking`, `reranker` and `reader` have been moved to `agno.knowledge`. See [examples]() for more details.

## Workflow updates

Updates to Memory

*   `add_memory_references` -> `add_memories`
*   `get_memory_references` -> `get_memories`
*   `delete_memory_references` -> `delete_memories`

Updates to Sessions

*   `add_session_summary_references` -> `add_session_summaries`
*   `get_session_summary_references` -> `get_session_summaries`
*   `delete_session_summary_references` -> `delete_session_summaries`

Updates to Workflow Class

*   `workflow_id` -> `id`
*   If `workflow_id` is passed, it will be ignored and `id` will be used instead.

Updates to Input & Output

*   Changed `message` to `input` in `WorkflowRunOutput`.

Updates to Sessions

*   Removed `session_name` and replaced with `name`.
*   Removed `session_description` and replaced with `description`.
*   Removed `session_tags` and replaced with `tags`.
*   Removed `session_metadata` and replaced with `metadata`.
*   Removed `session_created_at` and replaced with `created_at`.
*   Removed `session_updated_at` and replaced with `updated_at`.
*   Removed `session_last_run_at` and replaced with `last_run_at`.
*   Removed `session_last_run_status` and replaced with `last_run_status`.
*   Removed `session_last_run_id` and replaced with `last_run_id`.
*   Removed `session_last_run_output` and replaced with `last_run_output`.
*   Removed `session_last_run_error` and replaced with `last_run_error`.
*   Removed `session_last_run_metrics` and replaced with `last_run_metrics`.
*   Removed `session_last_run_duration` and replaced with `last_run_duration`.
*   Removed `session_last_run_total_tokens` and replaced with `last_run_total_tokens`.
*   Removed `session_last_run_input_tokens` and replaced with `last_run_input_tokens`.
*   Removed `session_last_run_output_tokens` and replaced with `last_run_output_tokens`.
*   Removed `session_last_run_cost` and replaced with `last_run_cost`.
*   Removed `session_last_run_currency` and replaced with `last_run_currency`.
*   Removed `session_last_run_model` and replaced with `last_run_model`.
*   Removed `session_last_run_provider` and replaced with `last_run_provider`.
*   Removed `session_last_run_api_key` and replaced with `last_run_api_key`.
*   Removed `session_last_run_api_base` and replaced with `last_run_api_base`.
*   Removed `session_last_run_api_version` and replaced with `last_run_api_version`.
*   Removed `session_last_run_api_type` and replaced with `last_run_api_type`.
*   Removed `session_last_run_api_deployment_name` and replaced with `last_run_api_deployment_name`.
*   Removed `session_last_run_api_engine` and replaced with `last_run_api_engine`.
*   Removed `session_last_run_api_model_name` and replaced with `last_run_api_model_name`.
*   Removed `session_last_run_api_embedding_model_name` and replaced with `last_run_api_embedding_model_name`.
*   Removed `session_last_run_api_embedding_model_provider` and replaced with `last_run_api_embedding_model_provider`.
*   Removed `session_last_run_api_embedding_model_api_key` and replaced with `last_run_api_embedding_model_api_key`.
*   Removed `session_last_run_api_embedding_model_api_base` and replaced with `last_run_api_embedding_model_api_base`.
*   Removed `session_last_run_api_embedding_model_api_version` and replaced with `last_run_api_embedding_model_api_version`.
*   Removed `session_last_run_api_embedding_model_api_type` and replaced with `last_run_api_embedding_model_api_type`.
*   Removed `session_last_run_api_embedding_model_api_deployment_name` and replaced with `last_run_api_embedding_model_api_deployment_name`.
*   Removed `session_last_run_api_embedding_model_api_engine` and replaced with `last_run_api_embedding_model_api_engine`.
*   Removed `session_last_run_api_embedding_model_api_model_name` and replaced with `last_run_api_embedding_model_api_model_name`.
*   Removed `session_last_run_api_embedding_model_api_embedding_model_api_key` and replaced with `last_run_api_embedding_model_api_embedding_model_api_key`.
*   Removed `session_last_run_api_embedding_model_api_embedding_model_api_base` and replaced with `last_run_api_embedding_model_api_embedding_model_api_base`.
*   Removed `session_last_run_api_embedding_model_api_embedding_model_api_version` and replaced with `last_run_api_embedding_model_api_embedding_model_api_version`.
*   Removed `session_last_run_api_embedding_model_api_embedding_model_api_type` and replaced with `last_run_api_embedding_model_api_embedding_model_api_type`.
*   Removed `session_last_run_api_embedding_model_api_embedding_model_api_deployment_name` and replaced with `last_run_api_embedding_model_api_embedding_model_api_deployment_name`.
*   Removed `session_last_run_api_embedding_model_api_embedding_model_api_engine` and replaced with `last_run_api_embedding_model_api_embedding_model_api_engine`.
*   Removed `session_last_run_api_embedding_model_api_embedding_model_api_model_name` and replaced with `last_run_api_embedding_model_api_embedding_model_api_model_name`.

Was this page helpful? Yes No

Agno Install & Setup Agno v2.0 Migration Guide

github discord youtube website

Powered by Mintlify

