# Agno Teams Session and Team Run Response Documentation




# Team Session

## TeamSession Attributes

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `session_id` | `str` | Required | Session UUID |
| `team_id` | `Optional[str]` | `None` | ID of the team that this session is associated with |
| `user_id` | `Optional[str]` | `None` | ID of the user interacting with this team |
| `workflow_id` | `Optional[str]` | `None` | ID of the workflow that this session is associated with |
| `team_data` | `Optional[Dict[str, Any]]` | `None` | Team Data: name, team\_id, model, and mode |
| `session_data` | `Optional[Dict[str, Any]]` | `None` | Session Data: session\_state, images, videos, audio |
| `metadata` | `Optional[Dict[str, Any]]` | `None` | Metadata stored with this team |
| `runs` | `Optional[List[Union[TeamRunOutput, RunOutput]]]` | `None` | List of all runs in the session |
| `summary` | `Optional[SessionSummary]` | `None` | Summary of the session |
| `created_at` | `Optional[int]` | `None` | The unix timestamp when this session was created |
| `updated_at` | `Optional[int]` | `None` | The unix timestamp when this session was last updated |

## TeamSession Methods

### `upsert_run(run: TeamRunOutput)`

Adds a TeamRunOutput to the runs list. If a run with the same `run_id` already exists, it updates the existing run.

### `get_run(run_id: str) -> Optional[RunOutput]`

Retrieves a specific run by its `run_id`.

### `get_messages_from_last_n_runs(...) -> List[Message]`

Gets messages from the last N runs with various filtering options:

*   `agent_id`: Filter by agent ID
*   `team_id`: Filter by team ID
*   `last_n`: Number of recent runs to include
*   `skip_role`: Skip messages with specific role
*   `skip_status`: Skip runs with specific statuses
*   `skip_history_messages`: Whether to skip history messages

### `get_session_summary() -> Optional[SessionSummary]`

Get the session summary for the session

### `get_chat_history() -> List[Message]`

Get the chat history for the session




# TeamRunOutput

The `TeamRunOutput` class represents the response from a team run, containing both the team’s overall response and individual member responses. It supports streaming and provides real-time events throughout the execution of a team.

## TeamRunOutput Attributes

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `content` | `Any` | `None` | Content of the response |
| `content_type` | `str` | `"str"` | Specifies the data type of the content |
| `messages` | `List[Message]` | `None` | A list of messages included in the response |
| `metrics` | `Metrics` | `None` | Usage metrics of the run |
| `model` | `str` | `None` | The model used in the run |
| `model_provider` | `str` | `None` | The model provider used in the run |
| `member_responses` | `List[Union[TeamRunOutput, RunOutput]]` | `[]` | Responses from individual team members |
| `run_id` | `str` | `None` | Run Id |
| `team_id` | `str` | `None` | Team Id for the run |
| `team_name` | `str` | `None` | Name of the team |
| `session_id` | `str` | `None` | Session Id for the run |
| `parent_run_id` | `str` | `None` | Parent run ID if this is a nested run |
| `tools` | `List[ToolExecution]` | `None` | List of tools provided to the model |
| `images` | `List[Image]` | `None` | List of images from member runs |
| `videos` | `List[Video]` | `None` | List of videos from member runs |
| `audio` | `List[Audio]` | `None` | List of audio snippets from member runs |
| `response_audio` | `Audio` | `None` | The model’s raw response in audio |
| `input` | `TeamRunInput` | `None` | Input media and messages from user |
| `reasoning_content` | `str` | `None` | Any reasoning content the model produced |
| `citations` | `Citations` | `None` | Any citations used in the response |
| `model_provider_data` | `Any` | `None` | Model provider specific metadata |
| `metadata` | `Dict[str, Any]` | `None` | Additional metadata for the run |
| `references` | `List[MessageReferences]` | `None` | Message references |
| `additional_input` | `List[Message]` | `None` | Additional input messages |
| `reasoning_steps` | `List[ReasoningStep]` | `None` | Reasoning steps taken during execution |
| `reasoning_messages` | `List[Message]` | `None` | Messages related to reasoning |
| `created_at` | `int` | Current timestamp | Unix timestamp of the response creation |
| `events` | `List[Union[RunOutputEvent, TeamRunOutputEvent]]` | `None` | List of events that occurred during the run |
| `status` | `RunStatus` | `RunStatus.running` | Current status of the run |
| `workflow_step_id` | `str` | `None` | FK: Points to StepOutput.step\_id |

## TeamRunOutputEvent Types

The following events are sent by the `Team.run()` function depending on the team’s configuration:

### Core Events

| Event Type | Description |
| --- | --- |
| `TeamRunStarted` | Indicates the start of a team run |
| `TeamRunContent` | Contains the model’s response text as individual chunks |
| `TeamRunIntermediateContent` | Contains intermediate content during the run |
| `TeamRunCompleted` | Signals successful completion of the team run |
| `TeamRunError` | Indicates an error occurred during the team run |
| `TeamRunCancelled` | Signals that the team run was cancelled |
| Event Type | Description |
| --- | --- |
| `TeamToolCallStarted` | Indicates the start of a tool call |
| `TeamToolCallCompleted` | Signals completion of a tool call, including tool call results |

### Reasoning Events

| Event Type | Description |
| --- | --- |
| `TeamReasoningStarted` | Indicates the start of the team’s reasoning process |
| `TeamReasoningStep` | Contains a single step in the reasoning process |
| `TeamReasoningCompleted` | Signals completion of the reasoning process |

### Memory Events

| Event Type | Description |
| --- | --- |
| `TeamMemoryUpdateStarted` | Indicates that the team is updating its memory |
| `TeamMemoryUpdateCompleted` | Signals completion of a memory update |

## Event Attributes

### Base TeamRunOutputEvent

All events inherit from `BaseTeamRunEvent` which provides these common attributes:
| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `created_at` | `int` | Current timestamp | Unix timestamp of the event creation |
| `event` | `str` | `""` | The type of event |
| `team_id` | `str` | `""` | ID of the team generating the event |
| `team_name` | `str` | `""` | Name of the team generating the event |
| `run_id` | `Optional[str]` | `None` | ID of the current run |
| `session_id` | `Optional[str]` | `None` | ID of the current session |
| `workflow_id` | `Optional[str]` | `None` | ID of the workflow |
| `workflow_run_id` | `Optional[str]` | `None` | ID of the workflow’s run |
| `step_id` | `Optional[str]` | `None` | ID of the workflow step |
| `step_name` | `Optional[str]` | `None` | Name of the workflow step |
| `step_index` | `Optional[int]` | `None` | Index of the workflow step |
| `content` | `Optional[Any]` | `None` | For backwards compatibility |

### RunStartedEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamRunStarted"` | Event type |
| `model` | `str` | `""` | The model being used |
| `model_provider` | `str` | `""` | The provider of the model |

### IntermediateRunContentEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamRunIntermediateContent"` | Event type |
| `content` | `Optional[Any]` | `None` | Intermediate content of the response |
| `content_type` | `str` | `"str"` | Type of the content |

### RunContentEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamRunContent"` | Event type |
| `content` | `Optional[Any]` | `None` | The content of the response |
| `content_type` | `str` | `"str"` | Type of the content |
| `reasoning_content` | `Optional[str]` | `None` | Reasoning content produced |
| `citations` | `Optional[Citations]` | `None` | Citations used in the response |
| `model_provider_data` | `Optional[Any]` | `None` | Model provider specific metadata |
| `response_audio` | `Optional[Audio]` | `None` | Model’s audio response |
| `image` | `Optional[Image]` | `None` | Image attached to the response |
| `references` | `Optional[List[MessageReferences]]` | `None` | Message references |
| `additional_input` | `Optional[List[Message]]` | `None` | Additional input messages |
| `reasoning_steps` | `Optional[List[ReasoningStep]]` | `None` | Reasoning steps |
| `reasoning_messages` | `Optional[List[Message]]` | `None` | Reasoning messages |

### RunCompletedEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamRunCompleted"` | Event type |
| `content` | `Optional[Any]` | `None` | Final content of the response |
| `content_type` | `str` | `"str"` | Type of the content |
| `reasoning_content` | `Optional[str]` | `None` | Reasoning content produced |
| `citations` | `Optional[Citations]` | `None` | Citations used in the response |
| `model_provider_data` | `Optional[Any]` | `None` | Model provider specific metadata |
| `images` | `Optional[List[Image]]` | `None` | Images attached to the response |
| `videos` | `Optional[List[Video]]` | `None` | Videos attached to the response |
| `audio` | `Optional[List[Audio]]` | `None` | Audio snippets attached to the response |
| `response_audio` | `Optional[Audio]` | `None` | Model’s audio response |
| `references` | `Optional[List[MessageReferences]]` | `None` | Message references |
| `additional_input` | `Optional[List[Message]]` | `None` | Additional input messages |
| `reasoning_steps` | `Optional[List[ReasoningStep]]` | `None` | Reasoning steps |
| `reasoning_messages` | `Optional[List[Message]]` | `None` | Reasoning messages |
| `member_responses` | `List[Union[TeamRunOutput, RunOutput]]` | `[]` | Responses from individual team members |
| `metadata` | `Optional[Dict[str, Any]]` | `None` | Additional metadata |
| `metrics` | `Optional[Metrics]` | `None` | Usage metrics of the run |
| `status` | `RunStatus` | `RunStatus.running` | Final status of the run |
| `workflow_step_id` | `Optional[str]` | `None` | FK: Points to StepOutput.step\_id |

### RunErrorEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamRunError"` | Event type |
| `error` | `str` | `""` | Error message |

### RunCancelledEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamRunCancelled"` | Event type |

### ToolCallStartedEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamToolCallStarted"` | Event type |
| `tool_name` | `str` | `""` | Name of the tool being called |
| `tool_args` | `Dict[str, Any]` | `{}` | Arguments passed to the tool |

### ToolCallCompletedEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamToolCallCompleted"` | Event type |
| `tool_name` | `str` | `""` | Name of the tool that was called |
| `tool_args` | `Dict[str, Any]` | `{}` | Arguments passed to the tool |
| `tool_result` | `Any` | `None` | Result returned by the tool |

### ReasoningStartedEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamReasoningStarted"` | Event type |

### ReasoningStepEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamReasoningStep"` | Event type |
| `step` | `ReasoningStep` | `None` | The reasoning step |

### ReasoningCompletedEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamReasoningCompleted"` | Event type |

### MemoryUpdateStartedEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamMemoryUpdateStarted"` | Event type |

### MemoryUpdateCompletedEvent

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `event` | `str` | `"TeamMemoryUpdateCompleted"` | Event type |



