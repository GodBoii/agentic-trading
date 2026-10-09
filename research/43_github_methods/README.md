# GitHub method review and fixed local experiments

This track reviews source files in six working repositories and records one public stub. It tests two new mechanisms and one fixed combination against the same local observations and execution engine used in earlier work.

Read `sources.md` for inspected formulas and the distinction between repository behavior and our adaptations. Read `hypotheses.md` for the specification frozen before replay. `findings.md` records outcomes and limits when the run completes.

Run from the repository root:

```powershell
python -m unittest research.43_github_methods.test_strategy -v
python -m research.43_github_methods.run
python -m research.43_github_methods.analyze
```

The replay command deliberately refuses to overwrite `runs/initial-v1`. The source fetcher also refuses to overwrite `upstream`. Preserve the first run and choose a new explicit specification/run name for subsequent experiments. `bars.py` copies the existing completed-minute validator from track 17 so the shared runner's source snapshot contains the entire policy dependency.

Evidence includes pinned inert source files and hashes, the frozen text and hash in `plan.json`, local normalized input hashes, a source snapshot, session summaries, trade ledgers, aggregate comparisons and the replay log. These experiments cannot authorize live trading or modify production agents.
