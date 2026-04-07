Your instinct is right: [universe_scanner.py](c:/Users/prajw/Downloads/Trader/python-backend/universe_scanner.py) is already doing too many jobs for the system you’re planning to build.

For a one-off prototype, one big file is fine. For the Dockerized end-to-end backend you described, it will become a bottleneck very quickly because different stages have different timing, data needs, failure modes, and parallelism rules. So if we are about to complete Stage 2 properly, this is the right moment to split responsibilities before the file turns into the whole backend.

**First principle**

Your system is not “one script that scans stocks.”

It is really 3 layers:
1. `data layer`
2. `pipeline layer`
3. `runtime/orchestration layer`

If we mix those in one file, Docker deployment becomes messy. If we separate them, then later you can run:
- one process for the always-on Tier 1 scanner
- one process for champion caching / scoring
- one process for user-triggered Tier 2 analysis
- one process for execution / monitoring

That separation matches your architecture and Docker plan.

**What Stage 2 completion means architecturally**

Stage 2 is not just “add a few more filters.”  
It introduces live intraday microstructure checks:
- spread
- tick activity
- time-of-day liquidity normalization
- possibly quote/depth snapshots

That means the scanner now needs both:
- historical daily/intraday data
- live quote/depth data

Once a file starts doing both universe filtering and live market microstructure logic, that is the point where splitting is justified.

So my answer is: yes, we should split the current file.

**How I would split the Python backend**

I would not split by “number of lines.”  
I would split by job responsibility.

Recommended structure:

1. `python-backend/services/dhan_client.py`
- single place for Dhan auth/context/client creation
- provides reusable helpers for:
  - historical data
  - quote data
  - ohlc batch data
  - market depth
- every other module imports from here
- this avoids repeating env loading and Dhan initialization everywhere

2. `python-backend/services/universe_loader.py`
- loads `BSE_LIST.json`
- applies static universe constraints
- returns clean BSE universe
- later can also load sector mappings, corp-action exclusions, etc.

3. `python-backend/services/surveillance_filter.py`
- downloads/parses ASM/GSM
- exposes simple checks like:
  - `is_gsm(security_id)`
  - `is_asm(security_id)`
- keeps BSE-watchlist logic out of scanner logic

4. `python-backend/stages/stage1_sanitation.py`
- owns Stage 1 only
- input: full BSE universe
- output: stage1 survivors
- should do:
  - ASM/GSM exclusion
  - corp action exclusion later
  - price range prefilter
  - broad daily liquidity and ATR sanity
- should save output file, for example `stage1_universe.json`

5. `python-backend/stages/stage2_liquidity_gate.py`
- owns Stage 2 only
- input: Stage 1 survivors
- output: Stage 2 survivors
- should do:
  - ADV threshold
  - spread threshold
  - tick activity threshold
  - time-of-day volume normalization
  - execution-quality checks
- save `stage2_liquid_universe.json`

6. `python-backend/stages/stage3_momentum_ignition.py`
- input: Stage 2 survivors
- output: momentum candidates
- RVOL, VWAP, opening range expansion, volume acceleration

7. `python-backend/stages/stage4_regime.py`
- computes market regime independently
- does not need per-stock full processing first
- output: regime tag + dynamic weights

8. `python-backend/stages/champion_selector.py`
- combines Stage 3 signals with Stage 4 regime
- scores candidates
- writes top 1-3 to cache/file/store

9. `python-backend/runtime/tier1_loop.py`
- orchestration script for the always-on background engine
- this is what Docker runs continuously for Tier 1
- it calls stages in sequence at the right cadence

10. `python-backend/runtime/tier2_trade_session.py`
- user-triggered deep analysis flow
- consumes champion cache
- runs agents / CIO / risk gate / execution later

**Which parts run one by one vs parallel**

This is the key design question.

Run sequentially:
1. Stage 1 -> Stage 2 -> Stage 3 -> Stage 4 -> champion selector
- because each stage narrows the input to the next
- this is the funnel

Run parallel inside a stage:
- per-stock evaluation within that stage
- especially in:
  - Stage 1 historical filters
  - Stage 2 live liquidity checks
  - Stage 3 momentum calculations

So the rule is:
- stages run in order
- stock processing inside a stage runs in parallel

That is the cleanest model.

**What should run at what frequency**

This is important for Docker/runtime efficiency.

Runs once pre-market:
- refresh BSE universe if needed
- ASM/GSM
- corp actions
- Stage 1 sanitation baseline

Runs every 10 minutes:
- Stage 2 liquidity gate
- Stage 3 momentum ignition
- Stage 4 regime refresh
- champion selection

Runs on-demand:
- Tier 2 agent swarm
- execution decision
- trade monitoring escalation

Runs continuously if trading:
- order monitoring
- kill switch
- open-position management

**What the Docker containers/processes should eventually look like**

You said later you’ll dockerize the whole backend.  
Given that plan, I would aim for this model:

1. `scanner` container/process
- runs `tier1_loop.py`
- always on during market hours
- updates stage outputs and champion cache

2. `api` container/process
- serves frontend/backend requests
- returns latest candidates, regime, stage outputs

3. `execution` container/process
- only active when user starts trading
- handles Tier 2, risk gate, order placement, monitoring

At the beginning, these can still be one Docker container with multiple Python entrypoints.  
But code should be split as if they may become separate later.

**What to do with current `universe_scanner.py`**

Do not keep growing it.

It currently mixes:
- universe loading
- surveillance ingestion
- Dhan data fetching
- filtering logic
- output writing
- runtime orchestration
- CLI behavior

That is too many responsibilities for the architecture you want.

Best move:
- keep it temporarily as a reference
- extract its logic into Stage 1 module + shared services
- then either delete it later or turn it into a thin wrapper that calls Stage 1

So I would not continue building the full system in that single file.

**Concrete implementation sequence I would follow next**

1. Extract shared Dhan client/auth code
2. Extract universe loading from `BSE_LIST.json`
3. Extract ASM/GSM service
4. Refactor current scanner into `stage1_sanitation.py`
5. Build `stage2_liquidity_gate.py` as a separate module
6. Add a `tier1_loop.py` orchestrator that runs Stage 1 and Stage 2 in the correct order
7. Only after that start Stage 3

This gives you a strong spine for the rest of the backend.

**Why this is the right time to refactor**
Because Stage 2 introduces:
- live quote/depth data
- repeated timed scans
- new output artifacts
- new performance constraints

If we delay splitting until Stage 3 or Stage 4, refactoring will be harder and riskier.

**Bottom line**

For the Dockerized end-to-end system you want, the correct approach is:
- split by stage and service responsibility now
- run stages sequentially
- process stocks in parallel within each stage
- keep Tier 1 as an always-on orchestrated loop
- keep Tier 2 separate and user-triggered

So my recommendation is not “add more to `universe_scanner.py`.”  
My recommendation is: use this moment to convert it into a modular Tier 1 pipeline before implementing the rest of Stage 2.

If you want, next I can give you the exact proposed file tree and responsibility contract for each file before we write any code.