# DeepSeek V4 vision model evaluation and selection

Date: 24 August 2026  
Workspace: `C:/Users/prajw/Downloads/Trader`

## Outcome

The stock-agent multimodal model was changed to:

`deepseek/deepseek-v4-flash-vision-exp`

This model produced the strongest complete replay among the tested models. It completed all 44 archived August 21 scenarios, passed the chart-reading gate with 12 correct checks out of 12, and produced a positive theoretical result from its chosen target and stop distances.

The OpenRouter API key in `python-backend/.env` was replaced with the user-supplied paid-account key. The key is deliberately omitted from this document.

## Original August 21 investigation

The last live-trading session on 21 August 2026 contained 44 stock-agent runs across 42 unique stocks. I joined three recorded sources:

- Supabase `agno_sessions` rows containing each agent prompt, response, reasoning, tool call, and immediate broker response.
- `python-backend/results/stage2/2026-08-21/setup-events.jsonl`, containing the system event that sent each stock to an agent.
- `python-backend/results/stage2/2026-08-21/one-second`, containing the recorded one-second market snapshots.

The 44 live runs broke down as follows:

- 19 agents placed no trade.
- 25 agents proposed an order.
- 21 order calls reached the broker.
- 5 were immediately reported `TRADED`.
- 7 were reported `PENDING`.
- 8 were reported `TRANSIT`.
- 1 was rejected.
- 4 proposed orders never reached the broker.

The five orders immediately reported as filled all touched their recorded stop before their target in the later one-second price sequence. This is a market-path observation, not a statement about the broker's final trade book.

The first audit site is stored in `august-21-trade-review/`. It shows all 44 agent runs, system trigger times and prices, original agent responses, immediate broker status, and annotated 15-minute candles.

## Vision comprehension tests

Every model received the same archived Kiri Industries 15-minute chart. The test checked 12 visible facts:

- Stock name
- Timeframe
- Data timestamp
- Last price
- VWAP
- ATR 14
- Partial-candle status
- Price relative to VWAP
- EMA 9 relative to EMA 21
- Previous-day high
- Previous-day close
- Previous-day low

Results:

| Model | Score | Result |
|---|---:|---|
| `stealth/ox-alpha` | 12/12 | Passed |
| `minimax/minimax-m3` | 11/12 | Passed, missed previous-day high |
| `moonshotai/kimi-k2.6` | 12/12 | Passed |
| `deepseek/deepseek-v4-flash-vision-exp` | 12/12 | Passed |

The first DeepSeek request using the old OpenRouter key was blocked by that account's privacy and provider restrictions. The user supplied a different paid-account key. DeepSeek worked with that key and passed 12/12.

Vision-test results are saved under `model-vision-tests/`.

## Historical replay method

The replay was intentionally isolated from live trading.

For every model and every available run:

1. The script loaded the original August 21 system message and user message from the archived Agno run.
2. It attached the same nine archived chart images in the same order:
   - Current 1-minute chart
   - Current 5-minute chart
   - Current 15-minute chart
   - Previous-session 5-minute chart
   - Previous-session 15-minute chart
   - Volume and participation
   - Momentum and volatility
   - OHLCV-derived price-structure liquidity
   - Current and previous TPO profile
3. It preserved the historical time, account context, market state, technical data, and risk budget.
4. It supplied one tool named `execute_trade_super_order`.
5. That tool only recorded a simulated protected order. It had no Dhan client, broker credentials, or order endpoint.
6. No input, output, or reasoning token limit was sent to OpenRouter.
7. Orders required side, quantity, entry, target, stop, order type, and rationale.
8. Invalid BUY or SELL price geometry was rejected by the simulator.

The replay outcome evaluator used the exact recorded one-second last-price sequence after the historical signal. It determined whether the entry became marketable or was later touched, then recorded whether target or stop came first.

## Replay results

| Model | Completed | Trades | Passes | Target first | Stop first | Other | Theoretical total |
|---|---:|---:|---:|---:|---:|---|---:|
| `stealth/ox-alpha` | 36/44 | 28 | 8 | 9 | 16 | 2 no exit, 1 untouched entry | +4.01R |
| `minimax/minimax-m3` | 44/44 | 9 | 35 | 1 | 7 | 1 untouched entry | -4.87R |
| `moonshotai/kimi-k2.6` | 44/44 | 9 | 35 | 3 | 6 | none | -1.23R |
| `deepseek/deepseek-v4-flash-vision-exp` | 44/44 | 14 | 30 | 6 | 8 | none | +3.76R |

The theoretical R total treats a stop as minus 1R and a target as the order's proposed reward divided by proposed risk. It excludes brokerage, taxes, spread, slippage, partial fills, market impact, trailing behavior, and any broker execution differences.

Ox Alpha had a slightly larger theoretical total, but it returned only 36 usable uncapped responses. Its shared upstream provider repeatedly rate-limited or returned embedded errors. DeepSeek completed all 44 and was the only complete model with a positive theoretical total.

## DeepSeek-specific observations

DeepSeek made 14 simulated trades and passed on 30 stocks.

- 6 trades touched target before stop.
- 8 trades touched stop before target.
- All 14 order payloads were structurally valid.
- No response was incomplete.
- Vision comprehension scored 12/12.
- Total recorded OpenRouter cost for the 44-run replay was about USD 0.16.

DeepSeek traded against the system direction four times:

- Aye Finance, system SHORT, model BUY
- Emmvee Photovoltaic Power, system SHORT, model BUY
- Asian Energy Services, system SHORT, model BUY
- Bata, system SHORT, model BUY

This remains a warning sign. Selecting DeepSeek does not mean the model should receive unrestricted live authority. The existing protected-order validation, cash limits, duplicate-order coordination, account checks, and stop requirements should remain in place.

## Sites and artifacts

Original audit:

- `august-21-trade-review/index.html`
- `august-21-trade-review/data.json`

Model replay sites:

- `ox-alpha-aug21-replay/index.html`
- `minimax-m3-aug21-replay/index.html`
- `kimi-k2-6-aug21-replay/index.html`
- `deepseek-v4-flash-vision-aug21-replay/index.html`

Each site uses:

- `model-replay-site/app.js`
- `model-replay-site/styles.css`

Replay data and resumable checkpoints live in each model's site directory.

## Scripts created

- `scripts/build_aug21_trade_review.py`
- `scripts/test_deepseek_v4_chart_vision.py`
- `scripts/run_paid_model_vision_tests.py`
- `scripts/replay_aug21_ox_alpha.py`
- `scripts/run_paid_model_replays.py`
- `scripts/evaluate_aug21_model_replays.py`
- `scripts/update_env_secret.py`

## Production configuration changes

Changed `python-backend/pipeline/llm/trading_model.py`:

- `DEFAULT_MULTIMODAL_MODEL_ID` now uses `deepseek/deepseek-v4-flash-vision-exp`.

Changed `python-backend/pipeline/config.py`:

- `multimodal_model_id` now uses `deepseek/deepseek-v4-flash-vision-exp`.

Changed `python-backend/.env`:

- Replaced `OPENROUTER_API_KEY` with the new paid-account key.
- Added `OPENROUTER_MULTIMODAL_MODEL_ID=deepseek/deepseek-v4-flash-vision-exp`.

The text model and regime model remain on their existing MiMo settings. The new model applies to the multimodal stock agent that reads the nine trading charts.

The running `ai-trading-agents` service was not restarted during this work. It will read the new key and model on its next process start. Restart it deliberately outside an active trading decision if an immediate switch is required.

## Verification

- All four replay datasets parse successfully.
- DeepSeek contains 44 completed runs, 14 valid orders, and no incomplete responses.
- The DeepSeek site renders 44 run cards and 14 trade-filter matches.
- Desktop and mobile layouts were checked.
- Canvas candlesticks and order annotations render.
- Browser console produced no errors.
- Python scripts compile.
- The supplied API key does not appear in generated replay data, progress notes, or source files outside the requested dotenv entry.

