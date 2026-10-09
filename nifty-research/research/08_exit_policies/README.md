# Whole-position option exits

This study compares fixed time, stop/target, trailing-stop and thesis-reversal exits on shared causal entries. It reads saved Nifty quotes and places no orders.

From `nifty-research` run:

```powershell
python research/08_exit_policies/study.py
python -m pytest research/08_exit_policies/test_exits.py -q --import-mode=importlib
```

The 36 configurations are two structures, three maximum holding periods and six exits. They share an entry schedule based on known five-minute futures momentum. No threshold is selected as optimal.

Read [the report](report.md), [sources](sources.md) and the [full table](artifacts/table.md). Results, paired comparisons, fixed contract ledgers and input hashes remain in `artifacts`. This study imports the quote and cost helpers from study 04 without modifying them.
