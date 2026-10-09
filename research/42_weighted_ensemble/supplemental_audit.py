"""Recover row identities and forecasts from frozen models without refitting."""

from bisect import bisect_left
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.common.data import AUDIT, VALIDATION, file_hash, load_manifest, load_ticks
from research.intraday_lab.domain import PolicyConfig, Tick
from .run import diagnostics, write
from .strategy import (CausalFeatures, Ensemble, FEATURE_NAMES, Ridge,
                       VARIANTS, executable_labels)


def restore_model(payload: dict | None) -> Ensemble | None:
    if payload is None:
        return None

    def ridge(value: dict) -> Ridge:
        return Ridge(tuple(value["columns"]), tuple(value["mean"]), tuple(value["scale"]),
                     tuple(tuple(row) for row in value["coefficients"]))

    model = Ensemble(tuple(payload["training_dates"]), payload["mode"],
                     tuple(ridge(value) for value in payload["specialists"]),
                     ridge(payload["joint"]), tuple(payload["weights"]), tuple(payload["constant_net"]))
    if json.dumps(asdict(model), sort_keys=True) != json.dumps(payload, sort_keys=True):
        raise ValueError("frozen model reconstruction changed fitted values")
    return model


def feature_hash(values: np.ndarray) -> str:
    values = np.ascontiguousarray(values, dtype="<f8")
    if values.shape != (len(FEATURE_NAMES),) or not np.isfinite(values).all():
        raise ValueError("row feature fingerprint requires five finite feature values")
    digest = sha256(json.dumps(list(FEATURE_NAMES), separators=(",", ":")).encode())
    digest.update(values.tobytes())
    return digest.hexdigest()


def interval_identities(ticks: list[Tick], config: PolicyConfig) -> tuple[np.ndarray, list[dict]]:
    """Repeat only original label admission logic to recover timestamps and symbols.

    Label prices/costs come from the unchanged original executable_labels function.
    Exact feature/order equality is checked before assigning any original label.
    """
    by_id: dict[int, list[Tick]] = {}
    for tick in ticks:
        by_id.setdefault(tick.security_id, []).append(tick)
    xs, identities = [], []
    for observations in by_id.values():
        times = [tick.at_us for tick in observations]
        if any(a >= b for a, b in zip(times, times[1:])):
            raise ValueError("label identities require strictly increasing instrument times")
        features = CausalFeatures(config)
        bad_prefix = [0]
        for index, tick in enumerate(observations):
            bad = not tick.usable(config.maximum_trade_age_seconds,
                                  receipt_proxy=config.freshness_mode == "receipt_proxy")
            bad |= index > 0 and tick.at_us - observations[index - 1].at_us > config.maximum_gap_seconds * 1e6
            bad_prefix.append(bad_prefix[-1] + int(bad))
        for index, decision in enumerate(observations):
            x, _ = features.update(decision)
            if x is None:
                continue
            entry_index = max(index + 1, bisect_left(times, decision.at_us + 250_000))
            if entry_index >= len(times):
                continue
            entry = observations[entry_index]
            exit_index = bisect_left(times, entry.at_us + 60_000_000)
            if (exit_index >= len(times) or entry.at_us - decision.at_us > 15_000_000
                    or observations[exit_index].at_us - entry.at_us > 75_000_000
                    or bad_prefix[exit_index + 1] != bad_prefix[index]):
                continue
            xs.append(x)
            identities.append({"security_id": decision.security_id, "symbol": decision.symbol,
                               "decision_us": decision.at_us, "label_entry_us": entry.at_us,
                               "label_exit_us": observations[exit_index].at_us})
    return np.asarray(xs).reshape(-1, len(FEATURE_NAMES)), identities


def evidence_digest(paths: tuple[Path, ...]) -> str:
    digest = sha256()
    for folder in paths:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                digest.update(str(path.relative_to(folder.parent)).encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    folder = Path(__file__).resolve().parent
    original = folder / "runs" / "initial-v1"
    training = folder / "models" / "initial-v1"
    output = folder / "supplemental" / "row-audit-v1"
    if output.exists():
        raise ValueError("supplemental evidence already exists; use a new audit version")
    original_digest = evidence_digest((original, training))
    reports = json.loads((training / "frozen-models.json").read_text(encoding="utf-8"))
    expected = json.loads((original / "forecast-diagnostics.json").read_text(encoding="utf-8"))
    plan = json.loads((original / "plan.json").read_text(encoding="utf-8"))
    for name in ("strategy.py", "run.py"):
        source = original / "source" / "research" / folder.name / name
        if (folder / name).read_bytes() != source.read_bytes():
            raise ValueError(f"live {name} differs from original frozen source")
    dependency = folder.parent / "08_statistical_models" / "strategy.py"
    if file_hash(dependency) != reports["receipt_proxy"]["feature_dependency_sha256"]:
        raise ValueError("original label dependency changed")
    models = {mode: restore_model(report["model"]) for mode, report in reports.items()}
    tables, checks = [], []
    for day in VALIDATION + AUDIT:
        ticks = load_ticks(day)
        input_hash = load_manifest(day)["cache_sha256"]
        if input_hash != plan["input_hashes"][day]:
            raise ValueError("evaluation cache differs from the original run")
        for mode, model in models.items():
            config = replace(PolicyConfig(), freshness_mode=mode)
            x, y, counts = executable_labels(ticks, config)
            recovered_x, identities = interval_identities(ticks, config)
            if not np.array_equal(x, recovered_x) or len(identities) != len(y):
                raise ValueError("reconstructed interval ordering or features differ from original labels")
            actual = diagnostics(model, x, y)
            prior = next(row for row in expected if row["date"] == day and row["mode"] == mode)
            if any(prior[key] != value for key, value in actual.items()):
                raise ValueError("frozen-model diagnostics differ from initial evidence")
            table = pd.DataFrame(identities, columns=["security_id", "symbol", "decision_us",
                                                      "label_entry_us", "label_exit_us"])
            table["date"], table["freshness_mode"] = day, mode
            table["role"] = "previously_inspected_historical_evaluation"
            table["model_status"] = "fitted" if model else "insufficient_training"
            table["input_sha256"] = input_hash
            table["frozen_models_sha256"] = file_hash(training / "frozen-models.json")
            table["feature_sha256"] = [feature_hash(row) for row in x]
            table["row_id"] = [sha256(f"{day}|{mode}|{row['security_id']}|{row['decision_us']}".encode()).hexdigest()
                               for row in identities]
            for index, name in enumerate(FEATURE_NAMES):
                table[f"feature_{name}"] = x[:, index]
            table["label_long_net_bps"], table["label_short_net_bps"] = y[:, 0], y[:, 1]
            for variant in VARIANTS:
                prediction = model.predict(x, variant) if model else np.full((len(x), 2), np.nan)
                for index, side in enumerate(("long", "short")):
                    table[f"prediction_{variant}_{side}_net_bps"] = prediction[:, index]
            if table["row_id"].duplicated().any():
                raise ValueError("duplicate supplemental row identity")
            tables.append((f"{day}-{mode}.parquet", table))
            checks.append({"date": day, "mode": mode, "rows": len(table), **counts,
                           "feature_order_exact_match": True, "diagnostics_exact_match": True})
            print(json.dumps({"date": day, "mode": mode, "recovered_rows": len(table)}), flush=True)
    if evidence_digest((original, training)) != original_digest:
        raise ValueError("original evidence changed while reconstructing rows")
    output.mkdir(parents=True)
    files = []
    for name, table in tables:
        path = output / name
        table.to_parquet(path, index=False, compression="zstd")
        files.append({"file": name, "rows": len(table), "sha256": file_hash(path)})
    (output / "supplemental_audit-source.py").write_bytes(Path(__file__).read_bytes())
    write(output / "report.json", {"original_evidence_sha256": original_digest,
          "original_evidence_unchanged": True, "refit_or_tuning": False,
          "script_sha256": file_hash(Path(__file__)), "files": files, "checks": checks,
          "total_rows": sum(len(table) for _, table in tables),
          "semantics": ["one row per complete future-label interval, with all seven variant forecasts",
                        "null strict-mode forecasts mean no fitted model, not predicted zero return",
                        "labels use original fixed-notional 60-second aggressive execution proxy",
                        "row intervals do not include account admission, target/stop or size constraints",
                        "future-label completeness filters this audit ledger, never the causal trading policy",
                        "initial strategy, run, models and evaluation evidence remain untouched"]})


if __name__ == "__main__":
    main()
