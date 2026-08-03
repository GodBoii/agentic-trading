# Aetheria Android System Assistant Changelog

## 2026-07-16 — Native control safety, reliability, and UX foundation

### Scope and compatibility

- Kept these changes limited to the Android `system-assistant` route and its `MobileTools` bridge. The default web, desktop, coder, and computer-agent tool paths were not given mobile tools.
- Preserved the repository's Agno `2.0.5` dependency pin. Optional Agent settings are filtered against the installed Agno constructor so newer v2 options do not break older deployments.
- Kept the System Assistant as one focused Agno `Agent`; it was not converted to a `Team`, avoiding delegation overhead for latency-sensitive phone actions.
- Removed the Python `go_home` tool method and explicitly excluded `go_home` from the shared action contract. The native HOME implementation may remain for non-agent use, but model commands are rejected before dispatch because HOME closes the VoiceInteractionSession overlay and terminates the conversation.

### Agno v2 integration decisions

- Applied a `tool_call_limit` of 12 to prevent runaway mobile-control loops.
- Enabled one model retry, disabled Agno telemetry for this native assistant, disabled run media retention, and attached Android mobile-contract metadata when supported by the installed Agno v2 version.
- Added explicit instructions for postcondition verification, privacy-blocked results, user-action fallbacks, native confirmation, limited retries, and prohibited secret entry.
- Added user cancellation using Agno's `cancel_run(run_id)` API. Active runs are tracked by conversation and user, with a Redis cancellation signal so cancellation can propagate in multi-worker deployments.
- Added a distinct `cancelled` run state instead of reporting user cancellation as an execution failure.
- Used device-native confirmation as the authoritative HITL boundary. This matches Agno's external-execution/HITL model while keeping consequential Android actions on the device and compatible with the existing streaming runner.

### Backend mobile action contract

- Added `mobile_action_contract.py` with contract version 2, command/request TTLs, action risk metadata, mutability metadata, and confirmation policy metadata.
- Exposed `get_visible_ui_text`, `get_travel_estimate`, `prepare_navigation`, and `open_navigation`, which already had corresponding native implementations.
- Kept all mobile command payloads typed and versioned with a request ID, issue time, expiry time, action risk, conversation/message IDs, and authenticated bridge token.
- Added structured native results containing action, request ID, contract version, duration, status, outcome, error code, and retryability where applicable.
- Replaced wall-clock timeout measurement with monotonic timing and added bounded bridge-registration readiness waiting.

### Authenticated native bridge

- Added `register_mobile_bridge` and `mobile_bridge_registered` Socket.IO events.
- Native bridges now authenticate with the current access token and receive a random, expiring bridge token bound to the exact Socket.IO SID and user.
- HTTP assistant requests can enable native tools only when the supplied assistant SID is registered to the authenticated user.
- Every pending mobile request is stored temporarily in Redis and bound to its expected SID, user, action, and bridge token.
- Mobile results are rejected when the request is expired/unbound, comes from another socket, or has the wrong bridge token.
- Removed logging of full assistant socket payloads and native text input; logs now contain identifiers, action names, status, and input length only.

### Native authorization and idempotency

- Added `MobileActionPolicy.java`, mirroring contract version 2 and the backend action allowlist.
- Native code rejects missing IDs, unsupported actions, incompatible contracts, expired/future commands, and commands from an unauthenticated bridge.
- Added a 64-entry in-memory result cache so duplicate request IDs return the original result instead of repeating a device mutation.
- Added risk-aware confirmation for prepared messages, navigation, silent alarms/timers, disruptive setting changes, and high-consequence semantic taps.
- Added normalized outcomes: `completed`, `dispatched_unverified`, `waiting_for_user`, and `not_completed`.
- Added foreground-package postcondition verification after app launch.

### Confirmation and action-progress UX

- Added a native liquid-glass confirmation card with a short device-generated title, sanitized action summary, “Not now,” and “Allow once.” Model output cannot alter this policy decision.
- Added haptic feedback, accessible focus behavior, entrance/exit animation, timeout handling, and automatic rejection when the assistant closes.
- Added local action lifecycle states: received, waiting for user, executing, completed, unverified, or not completed.
- Added a visible stop button while the assistant is thinking. It rejects any pending confirmation, requests backend cancellation, stops voice playback/listening, and returns the overlay to a ready state when cancellation completes.

### Accessibility and screen privacy

- Added `MobilePrivacyGuard.java` for on-device accessibility redaction.
- Password-node text and content descriptions are now always omitted.
- Labeled OTPs, verification codes, passwords, private keys, recovery codes, CVVs/CVCs, and card-like numbers are redacted before leaving the accessibility layer.
- Screen reading, text entry, taps, swipes, and semantic clicks are blocked in credential, authenticator, banking, wallet/payment, and medical-record package contexts.
- Text entry is blocked whenever the focused accessibility node is a password field.
- Circle Search and Mindspace screenshot capture are blocked in protected app contexts with a user-facing explanation.
- Reduced AccessibilityService events from `typeAllMask` to window state/window content/window list/focus events, removed unused key-event filtering, and added a notification debounce.

### Android manifest hardening

- Removed duplicate permission declarations while retaining permissions used by existing assistant, audio, overlay, notification, location, and foreground-service features.
- Disabled Android application backup to reduce the risk of copying native authentication/session material into device backups.

### Tests and verification

- Added backend contract tests that verify every exposed action has a toolkit method, backend/native contract versions match, the native policy contains all exposed actions, and `go_home` remains unavailable.
- Added Android unit tests for sensitive-package classification and redaction behavior.
- Passed Python syntax compilation for all modified backend modules.
- Passed four backend mobile contract tests.
- Passed Android `:app:compileDebugJavaWithJavac` and `:app:testDebugUnitTest` using the Android Studio JetBrains Runtime 21.
- `git diff --check` passed. Existing unrelated user files and the pre-existing modified `android/app/src/main/cpp/llama.cpp` worktree were not changed.

### Physical-device verification still required

- Test confirmation-card positioning with gesture and three-button navigation, display scaling, and large fonts.
- Test the default-assistant overlay across Pixel, Samsung, OnePlus, and Xiaomi Android variants.
- Verify Socket.IO reconnect/bridge re-registration, cancellation during model inference, cancellation during native confirmation, and command deduplication on an actual device.
- Verify app-launch postconditions and protected-app detection against the final supported app/device matrix.

## 2026-07-16 — Continuous native-assistant microphone and backend DNS recovery

### Log analysis and root causes

- Correlated the supplied Android and Docker logs by timestamp. The power-button assistant repeatedly received Android `SpeechRecognizer` error 7 (`ERROR_NO_MATCH`) after roughly two seconds of initial silence, then recreated the recognizer, which caused the visible microphone on/off loop.
- Confirmed spoken phrases were transcribed on-device, but the subsequent assistant request failed before reaching the agent because Supabase JWT validation raised `httpx.ConnectError: [Errno -2] No address found`.
- Confirmed the same resolver failure caused the subscription, integrations, Composio, mobile bridge, and scheduled-task errors. The remaining Oplus/MediaTek/Gralloc messages in logcat are vendor framework diagnostics rather than Aetheria exceptions.

### Native microphone lifecycle

- Replaced the power-button assistant's OEM `SpeechRecognizer` loop with direct 16 kHz mono PCM `AudioRecord` capture.
- Removed the initial-silence timeout: the microphone now remains continuously active until the user begins speaking or closes/stops the assistant.
- Added adaptive on-device RMS voice activity detection, 600 ms pre-roll to preserve the first word, a short speech-start gate to reject clicks, and end-of-speech detection after one second of sustained silence.
- Kept a 90-second safety ceiling only after speech has started to bound memory and request size; this does not time out a user who has not started speaking.
- Releases the microphone immediately when end-of-speech is detected, creates a valid PCM WAV payload, and sends the recording to the existing authenticated `/api/mic/transcribe` endpoint.
- Sends the returned clean transcription through the existing `dispatchAssistantMessage` path, so the text reaches the same backend agent and conversation as typed/native assistant input.
- Added an `Understanding…` UI phase between microphone release and transcription completion without entering the normal THINKING transition prematurely (that transition intentionally cancels listening work).
- Added generation-based cancellation and stale-result rejection for assistant close, stop, and restart operations, including protection against an old microphone generation clearing a newly started capture.
- Replaced repeated automatic retries with actionable, non-looping permission, connection, authentication-service, usage-limit, and transcription errors.
- Avoided logging recorded audio or transcription content; only lifecycle identifiers and byte/text lengths are logged.

### Backend DNS and authentication resilience

- Set `EVENTLET_NO_GREENDNS=yes` both before Eventlet import and in the production Docker image, making Eventlet use the container/OS DNS resolver instead of the resolver path implicated by the supplied production logs.
- Consolidated REST and Socket.IO JWT validation into the same cache-aware helper.
- Added one short retry for transient Supabase DNS/transport failures.
- Changed exhausted infrastructure failures into a controlled `503 Authentication service temporarily unavailable` result instead of an uncaught exception, REST 500, Socket.IO traceback, or misleading expired-session response.
- Kept actual invalid/expired JWTs as 401 responses and never cached either credential failures or service outages.
- Preserved the existing five-minute Redis cache, SHA-256 token-keying, and safe cached user subset.
- These backend changes are transport-wide because the DNS failure affected multiple frontends and services; the new microphone implementation itself remains isolated to the Android native assistant.

### Tests and verification

- Added backend tests for retry exhaustion returning 503 and recovery on the second auth attempt.
- Added an Android unit test verifying the generated WAV container, mono PCM format, 16 kHz sample rate, 16-bit depth, data length, and exact sample preservation.
- Passed Python syntax compilation for the modified backend and assistant modules.
- Passed six focused backend tests (mobile action contract plus auth resilience).
- Passed Android `:app:compileDebugJavaWithJavac` and `:app:testDebugUnitTest`; all six Android unit tests passed, including the new microphone WAV test.
- A repository-wide local pytest collection was also attempted, but the developer Python environment lacks `boto3` and `redis`, which are production requirements used by unrelated legacy tests. The focused modified-area test suite passed.

### Deployment and physical-device verification required

- Rebuild/redeploy the backend container so `EVENTLET_NO_GREENDNS=yes` takes effect, then verify Supabase auth, scheduled tasks, subscription status, integrations, and assistant Socket.IO requests from the deployed network.
- Install the rebuilt Android app and verify indefinite pre-speech listening, first-word preservation, end-of-speech timing, noisy-room behavior, interruption by closing/stopping the overlay, and the complete voice → transcription → agent response flow on the target device.

## 2026-07-16 — Native Android speech recognition restored

### Superseding microphone architecture

- Removed the Android native assistant's `AudioRecord`, PCM/WAV creation, Base64 encoding, OkHttp audio request, and `/api/mic/transcribe` integration.
- Restored Android `SpeechRecognizer` as the native assistant's only speech-to-text implementation.
- Prefer Android's on-device recognizer on Android 12+ when the device reports it is available; otherwise use the installed Android system recognition service.
- Only Android's final recognized text is passed to `AssistantSession.dispatchAssistantMessage` and sent to the existing backend agent. The native assistant no longer sends recorded audio to the Aetheria backend or mic audio model.
- Kept the backend mic endpoint and `mic_agent.py` unchanged because the shared backend serves other frontends; the Android native assistant no longer references or calls them.

### Native recognition lifecycle

- Preserved partial native recognition results for responsive UI and as a fallback when Android returns an empty final result.
- Kept the `Understanding…` state while Android finalizes text after detecting end-of-speech.
- Added native on-device/system recognizer selection, main-thread lifecycle enforcement, stale delayed-restart cancellation, and bounded recovery for genuine service failures.
- Treat Android `ERROR_NO_MATCH` and `ERROR_SPEECH_TIMEOUT` as renewable idle recognition windows. Some OEM recognizers impose their own idle window even when silence extras are provided; the assistant silently renews the Android-native session without uploading audio or showing a conversation error.
- Kept actual permission, microphone, recognizer-busy, network, and native service failures separate and user-readable.
- Removed transcript content from native logs; only the recognized text length is logged.

### Verification

- Replaced the WAV-generation unit test with native-recognition tests covering renewable idle errors and Android-specific failure messaging.
- The earlier Supabase/Eventlet DNS and auth resilience fixes remain unchanged.
- `go_home` remains unavailable to the model.

## 2026-07-16 — System-assistant streaming, observability, and tool-run repair

### Supplied run diagnosis

- Correlated the screenshot with the supplied run from 21:38:20–21:38:54. The displayed “message got cut off” text was not a local fallback: it was provisional model prose streamed before the first mobile tool call.
- The backend then completed exactly 12 mobile tool calls, matching the configured tool-call ceiling, and produced no post-tool final answer. Android marked its response buffer for a future reset but did not clear the already-visible provisional text, so the stale sentence became the apparent final response while device automation continued.
- Confirmed token logging looked only for `TeamRunOutput`. The system assistant is an Agno `Agent`, and streaming returns `RunCompletedEvent` with metrics, so the completed metrics event was ignored. The database fallback then found no persisted Agno session row for this lightweight agent and skipped usage logging.
- Confirmed reasoning events were already emitted by the backend adapter, but the Android native bridge had no `reasoning_step` listener.

### Streaming lifecycle repair

- System-assistant prose emitted before a subsequent tool call is now treated as provisional and removed from the backend final-content accumulator.
- Added an `assistant_response_reset` event at tool start. Android handles it by immediately clearing its stream buffer and hiding the stale response card.
- Tool-start handling on Android now independently clears provisional content, making the client safe even if a reset event is delayed.
- Response-card show/hide animations now cancel stale end callbacks so a delayed tool-start fade cannot hide a newly arrived final response.
- Tool-end events now update the visible status instead of being discarded.
- When a tool run genuinely ends without post-tool model content, the backend emits a deterministic observed-state terminal message based on completed tools. It never guesses that a prepared message was sent or that an unverified action succeeded.
- The truthful terminal message is stored in run catch-up state and notification preview, preventing stale pre-tool text from returning after reconnect.

### Reasoning and debug visibility

- Added Android handling for backend `reasoning_step` events with a throttled, bounded “Thinking:” status display.
- Enabled Agno debug mode for the system assistant.
- Added a completion summary log with mode, tool count, content-chunk count, reasoning-event count, final-response length, and whether metrics were captured. Prompt and transcript content remain excluded from these lifecycle logs.

### Tool behavior

- Increased the bounded system-assistant tool-call limit from 12 to 20 so ordinary multi-screen mobile flows do not terminate at the previous ceiling.
- Added instructions not to re-ask for message details already supplied, not to narrate actions before executing tools, to avoid rereading unchanged screens, and always to provide one factual post-tool result.
- Preserved native confirmation and review boundaries for message preparation. `go_home` remains unavailable.

### Token accounting

- Added Agno `RunOutput` support and capture of streamed `RunCompleted`/`TeamRunCompleted` events carrying metrics.
- Token extraction now receives the completed Agent event instead of `None`, allowing the existing Convex usage logger to record input, output, and total usage supplied by Agno.
- Changed the optional Supabase session lookup from `single()` to `maybe_single()` so lightweight non-persisted agents do not generate a misleading PGRST116 warning if metrics genuinely require fallback lookup.

### Tests

- Added tests for conservative post-tool messages, read-after-write selection, failed tool handling, backend/Android response-reset integration, and completed-event metric capture wiring.

## 2026-07-25 — Phase 1: shared backend DNS and authentication stability

### Scope and compatibility

- Limited this phase to shared backend startup and JWT validation. Android microphone/STT, assistant UI, agent configuration, and mobile tools were not modified.
- Audited REST and Socket.IO consumers before changing the shared helper. The Android app and bundled web frontend both use these paths; the separate desktop and website clients use the same public backend contract.
- Preserved existing successful authentication results, 401 responses for invalid or expired tokens, the five-minute Redis cache, and cache write-through behavior.
- Confirmed from the installed Agno `Toolkit` implementation that only methods listed in the toolkit's `tools` constructor argument are registered. The existing `go_home` method is not in that list and remains unavailable to the model.

### DNS resolver fix

- Verified directly against the pinned Eventlet 0.36.1 wheel that `EVENTLET_NO_GREENDNS=yes` disables Eventlet's greendns socket overrides.
- Set `EVENTLET_NO_GREENDNS=yes` in the Docker image because Gunicorn imports its Eventlet worker before loading `app.py`.
- Set the same value with `os.environ.setdefault` before importing Eventlet in `app.py`, covering direct/local application startup while preserving an explicit operator override.
- Preserved all unrelated existing Dockerfile changes.

### Authentication resilience

- Added one bounded retry with a 200 ms cooperative delay for `httpx.TransportError`, including the `httpx.ConnectError: [Errno -2] No address found` failure seen in the supplied logs.
- Return `503 Authentication service temporarily unavailable` when both transport attempts fail instead of allowing REST 500 responses or Socket.IO handler tracebacks.
- Continue returning 401 immediately for Supabase `AuthApiError` and for a successful auth response that contains no user.
- Catch only HTTP transport failures. Unexpected programming or response-shape errors remain visible and are not converted into availability errors.
- Use the same validation path for HTTP Bearer-token and Socket.IO JWT authentication without changing either caller's existing response format.

### Tests and verification

- Added seven focused authentication tests covering transport retry recovery, retry exhaustion, REST 503 propagation, invalid-token 401 behavior, missing-user 401 behavior, Socket.IO cache write-through, and unexpected exception propagation.
- Focused Phase 1 authentication tests pass.
- Python syntax compilation passes for `app.py`, `utils.py`, `api.py`, `sockets.py`, `extensions.py`, and `factory.py`.
- `docker compose config --quiet` passes. Docker image lint/build could not run because the local Docker Desktop daemon is not running.
- Broader pre-existing tests still report unrelated mobile-action and assistant-stream contract failures; they were not changed in this phase.

### Deployment verification required

- Rebuild and redeploy the backend image so the container-level resolver setting is active.
- In staging, verify authenticated subscription, integrations, Composio, regular chat, Android assistant, and Socket.IO reconnect flows from all three frontends.
- Confirm scheduled-task polling no longer produces repeated `[Errno -2] No address found` errors.

## 2026-07-25 — Phase 2: Android-native microphone and STT lifecycle

### Scope

- Limited implementation changes to the Android native assistant's speech manager, its unit test, and Android 11 recognition-service package visibility.
- Did not modify the shared backend, `/api/mic/transcribe`, `mic_agent.py`, website/Electron mic behavior, Agno agents, or mobile tools.
- Preserved the existing session wiring: partial native results are shown with `showPartialInput`, and the final native transcript is shown with `showTranscription` before being sent through the existing Socket.IO/HTTP agent message path.
- `go_home` remains outside the registered Agno toolkit.

### Native STT implementation

- Replaced the old bounded OEM timeout loop with Android `SpeechRecognizer` lifecycle management.
- Prefer `SpeechRecognizer.createOnDeviceSpeechRecognizer` on Android 12+ when on-device recognition is available; otherwise use the installed Android system recognition service.
- Added `android.speech.RecognitionService` to the manifest `<queries>` block, as required for recognition-service visibility on Android 11+.
- Kept microphone audio entirely inside Android speech recognition. The native assistant does not create PCM/WAV payloads or call Whisper, OpenRouter mic transcription, or `/api/mic/transcribe`.
- Enabled partial results and free-form recognition using the device locale.
- Added post-speech silence hints of 1.2 seconds complete / 0.7 seconds possibly complete, while treating these values as recognizer hints rather than guaranteed OEM behavior.

### Lifecycle and reliability

- Treat `ERROR_NO_MATCH` and `ERROR_SPEECH_TIMEOUT` as renewable idle windows. They do not consume the bounded service retry budget or show a conversation error, so the assistant continues waiting until the user speaks or closes it.
- Use a partial transcript as the final result if an OEM recognizer ends with an idle/no-match error after already returning usable text.
- Added request generations and removable delayed-start callbacks so closing, stopping, or restarting the assistant invalidates stale recognition callbacks.
- Invalidate the old listener before cancellation, preventing a synchronous `ERROR_CLIENT` callback from restarting an obsolete session.
- Run recognizer creation, start, cancellation, and destruction on the supplied main-thread handler.
- Keep bounded retries for genuine recoverable Android service failures such as network, server, client, busy, and server-disconnected errors.
- Keep microphone, permission, unsupported-language, rate-limit, and other fatal failures user-readable without retry loops.
- Stop logging transcript content; lifecycle logs now contain only state, error codes, and transcript lengths.

### Tests and verification

- Started from a failing native STT test compilation because the expected idle-error and native-error helpers were missing.
- Added coverage for renewable idle errors, bounded service-error classification, permission/audio non-retry behavior, and native-only error messaging.
- Passed `:app:compileDebugJavaWithJavac`.
- Passed `:app:testDebugUnitTest`: eight Android unit tests, zero failures.
- Existing manifest warnings about duplicate permission declarations remain pre-existing and were not changed during this phase.

### Physical-device verification required

- Verify delayed speech across several automatic idle-window renewals.
- Verify partial and final transcript rendering, first-word capture, short commands, long commands, pauses, cancellation, overlay dismissal, and immediate restart.
- Verify on-device recognition selection on supported Android 12+ devices and system-recognizer fallback on devices without an on-device model.
- Test network loss when the fallback recognizer requires connectivity, plus microphone permission denial and recovery.
- Confirm final native text reaches the existing agent flow and that no native request is made to `/api/mic/transcribe`.

## 2026-07-25 — Phase 2 mic correction and Phase 3 native voice handoff

### Superseded behavior and root cause

- Supersedes Phase 2's renewable idle-window approach on Android 13 and newer.
- Physical-device logs showed that the installed OEM `SpeechRecognizer` closed each silent session after roughly one second. Renewing those sessions caused the visible start/stop microphone loop and could lose the beginning of speech.
- Found a separate lifecycle race where authentication could complete after the overlay was dismissed and transition the hidden assistant back to `LISTENING`.

### Continuous microphone session

- Added one uninterrupted Android `AudioRecord` session on Android 13+ using 16 kHz, mono, PCM16 audio.
- The microphone now waits without an initial-silence timeout. Speaking immediately or after an arbitrary silent delay uses the same capture session.
- Added local adaptive voice activity detection, a 600 ms pre-roll for first-word preservation, and one second of post-speech silence detection.
- The microphone is released as soon as end-of-speech is detected.
- Sends the captured PCM directly to Android's native `SpeechRecognizer` with `RecognizerIntent.EXTRA_AUDIO_SOURCE` and a segmented session. No Whisper model, OpenRouter audio flow, backend transcription endpoint, or audio upload was added.
- Retained the existing native `SpeechRecognizer` compatibility path below Android 13, where caller-provided native-recognition audio is unavailable.

### Overlay teardown

- Added overlay visibility generations so late authentication, delayed Circle Search, speech, and stale state callbacks cannot reactivate a closed assistant.
- Closing or destroying the overlay now invalidates the active speech generation, stops and releases `AudioRecord`, closes recognition pipe descriptors, unconditionally cancels and destroys `SpeechRecognizer`, stops TTS and the mobile bridge, and cancels in-flight Android HTTP calls.
- Invalidated canceled HTTP callback generations so an old response cannot appear if the assistant is reopened quickly.
- Kept hidden-session callbacks from updating UI, starting TTS, or returning to `LISTENING`.

### Phase 3 transcript and agent handoff

- Added an `Understanding...` processing state after end-of-speech while Android converts the captured audio to text.
- Native partial/segment text continues to render in the existing prompt UI.
- The final transcript continues through the existing `showTranscription` and Socket.IO/HTTP agent message flow; shared backend request contracts were not changed.
- `go_home` remains intentionally unexposed to the model.

### Tests and verification

- Started with a failing unit test for the Android 13+ continuous-capture policy.
- Passed `:app:testDebugUnitTest`: nine Android unit tests, zero failures.
- Passed `:app:assembleDebug`; the debug APK was generated successfully.
- `git diff --check` reports no whitespace errors.
- No online Android device was available through ADB, so microphone timing, OEM recognition of injected PCM, overlay dismissal, and immediate reopen still require physical-device verification.

## 2026-07-25 — Phase 4: assistant continuity, socket authorization, and log privacy

### Latest-run validation

- Confirmed from the supplied physical-device run that native speech produced both expected transcripts, reused one conversation ID, reached the system assistant, streamed responses, and completed both backend runs.
- Found that the second request incorrectly answered as if it were the first turn. The system assistant was explicitly constructed without a database, so `add_history_to_context=True` in the runner had no history to load.
- Found the complete Supabase JWT, its embedded profile claims, user prompts, model reasoning, and responses in production terminal logs.
- Found that Agno `Agent` completion metrics were still ignored because the runner only retained `TeamRunOutput`.

### Conversation continuity and stream correctness

- Added Agno `PostgresDb` persistence to the lightweight system assistant, scoped by the authenticated user and existing conversation ID.
- Added the most recent 12 runs to voice-assistant context while keeping long-term agentic/user memory disabled.
- Restored capture of both `RunOutput` and `TeamRunOutput`, including completed Agent events carrying metrics.
- Changed the optional Agno-session metrics fallback from `single()` to `maybe_single()` so a missing row does not create a misleading PGRST116 warning.
- Restored provisional-response reset at tool start. Android clears pre-tool prose immediately and the backend stores only post-tool final content.
- Restored conservative terminal messages when a mobile tool run ends without a post-tool answer.

### Socket authorization

- `join_conversation` now requires a valid Supabase token and verifies that the authenticated user owns the Redis session or run state before joining the room or receiving catch-up content.
- Regular chat and native assistant handlers now reject attempts to reuse another user's conversation ID before joining its room, changing its configuration, terminating it, or starting an agent run.
- Completed and failed run-state records now preserve `user_id`, allowing ownership checks to remain effective during reconnect/catch-up.
- Removed the unnecessary room join from Plan Mode, whose responses are emitted only to the requesting socket.
- Updated the web and Android clients to include the current access token when joining. Web chat messages also include the refreshed token so a long-lived socket cannot keep using an expired handshake token.
- Kept all existing Socket.IO event names and successful request/response shapes for Android, website, and desktop consumers.

### Log and browser privacy

- Replaced raw assistant socket payload logging with sanitized, length-bounded conversation/message IDs, message length, and a token-present boolean. Tokens, prompts, configuration values, profile claims, and log-control characters are not logged.
- Removed raw user-context payload/result logging.
- Made Agno debug logging opt-in with `AGNO_DEBUG_MODE=true`; it is disabled by default so production logs do not contain prompts, model reasoning, responses, or full system instructions.
- Removed browser auth logs containing user/session objects, signup email/name/phone metadata, call stacks, Supabase responses, and profile values.

### Tests and verification

- Added focused tests for socket log redaction, live-session/run-state ownership resolution, owner-only access, safe creation of unowned conversation IDs, preserved run-state ownership, persistent system-assistant history, Agent/Team metrics capture, and opt-in debug logging.
- Passed 21 focused backend tests covering Phase 4 security, authentication resilience, and assistant streaming.
- Passed Python syntax compilation for the modified security, socket, run-state, system-assistant, and agent-runner modules.
- Passed the production web build.
- Passed all nine Android unit tests and `:app:assembleDebug`.
- `go_home` remains absent from the registered mobile toolkit list.

### Deliberately deferred from this batch

- Did not change the deployed-site runtime SQL contract, OAuth integration bootstrap URLs, native token-at-rest storage, sandbox-manager trust boundary, or artifact rendering. Those cross-client changes require separate Phase 4 batches so they can be deployed and verified independently without breaking existing website or desktop flows.
