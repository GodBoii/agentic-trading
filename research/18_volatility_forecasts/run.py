"""Evaluate frozen EWMA and rolling forecasts on identical eligible minute pairs."""

from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
import platform

from research.common.data import DATES, load_manifest, load_ticks, phase

model = import_module("research.18_volatility_forecasts.model")


def main() -> None:
    root = Path(__file__).resolve().parent
    output = root/"runs/initial-v1"
    if output.exists():
        raise ValueError("preserve evidence, use a new run directory")
    manifests = {day:load_manifest(day) for day in DATES}
    output.mkdir(parents=True)
    source = output/"source"; source.mkdir()
    hashes = {}
    for path in root.glob("*.py"):
        content = path.read_bytes(); (source/path.name).write_bytes(content)
        hashes[path.name] = sha256(content).hexdigest()
    plan = {"dates":DATES,"models":list(model.MODEL_NAMES),"lambdas":[.94,.97],
            "rolling_returns":30,"warmup_returns":30,"variance_floor":model.FLOOR,
            "maximum_receipt_gap_seconds":15,"freshness_trade_age_seconds":5,
            "zero_mean_assumption":True,"outcome":"next completed minute squared log midpoint return",
            "forecast_clock":"minute boundary, uses receipts strictly before boundary",
            "qlike":"log(forecast_variance)+squared_return/forecast_variance",
            "input_hashes":{day:m["cache_sha256"] for day,m in manifests.items()},
            "source_hashes":hashes,"python":platform.python_version(),
            "promotion_eligible":False,"account_trades":0}
    (output/"plan.json").write_text(json.dumps(plan,indent=2),encoding="utf-8")
    summaries = []
    for day in DATES:
        ticks = load_ticks(day)
        (output/f"input-{day}.json").write_text(json.dumps(manifests[day],indent=2),encoding="utf-8")
        for mode in ("recent_trade","receipt_proxy"):
            bars,quality = model.completed_minutes(ticks,receipt_proxy=mode=="receipt_proxy")
            states = {}; pairs=[]
            for bar in bars:
                state = states.setdefault(bar.security_id,model.VarianceModel())
                pair = state.on_bar(bar)
                if pair is not None:
                    pairs.append(pair)
            counters = Counter()
            for state in states.values():
                counters.update(state.counts)
            stem = f"{day}-{mode}"
            pairs_file = output/f"pairs-{stem}.jsonl"
            with pairs_file.open("w",encoding="utf-8") as stream:
                for pair in pairs:
                    stream.write(json.dumps(pair,separators=(",",":"),allow_nan=False)+"\n")
            metrics=[]
            for name in model.MODEL_NAMES:
                scored=[model.losses(p["forecasts"][name],p["squared_log_return"]) for p in pairs]
                metrics.append({"model":name,"pairs":len(pairs),
                                "mse":sum(x[0] for x in scored)/len(scored) if scored else None,
                                "qlike_gaussian":sum(x[1] for x in scored)/len(scored) if scored else None,
                                "sum_squared_error":sum(x[0] for x in scored),
                                "sum_qlike_gaussian":sum(x[1] for x in scored)})
            summary={"date":day,"phase":phase(day),"mode":mode,"quality":quality,
                     "model_counters":dict(counters),"metrics":metrics,
                     "pairs_sha256":sha256(pairs_file.read_bytes()).hexdigest()}
            (output/f"summary-{stem}.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
            summaries.append(summary)
            print(json.dumps({"date":day,"mode":mode,"pairs":len(pairs),"valid_minutes":quality.get("valid_minutes",0)}),flush=True)
    aggregate=[]
    for mode in ("recent_trade","receipt_proxy"):
        for phase_name in ("all","development","validation_diagnostic","historical_audit"):
            selected=[s for s in summaries if s["mode"]==mode and (phase_name=="all" or s["phase"]==phase_name)]
            for name in model.MODEL_NAMES:
                metrics=[m for s in selected for m in s["metrics"] if m["model"]==name]
                n=sum(m["pairs"] for m in metrics)
                aggregate.append({"mode":mode,"phase":phase_name,"model":name,"pairs":n,
                                  "mse":sum(m["sum_squared_error"] for m in metrics)/n if n else None,
                                  "qlike_gaussian":sum(m["sum_qlike_gaussian"] for m in metrics)/n if n else None})
    (output/"aggregate.json").write_text(json.dumps(aggregate,indent=2),encoding="utf-8")


if __name__ == "__main__":
    main()
