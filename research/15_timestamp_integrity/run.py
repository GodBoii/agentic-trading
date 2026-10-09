"""Fixed-cohort read-only audit of archived decoded raw-depth captures."""

from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
import platform

import numpy as np
import pyarrow.parquet as pq

normalizer = import_module("research.15_timestamp_integrity.normalizer")
ROOT = Path(__file__).resolve().parents[2]
DATES = ("2026-08-28","2026-08-31","2026-09-01")


def audit(day: str, ids: set[int], output: Path, limit: int = 20_000) -> dict:
    if limit <= 0:
        raise ValueError("positive sample limit required")
    source = ROOT/"python-backend/results/stage2"/day/"raw-depth"
    paths = sorted(source.rglob("*.parquet"))
    counts = Counter()
    types = Counter()
    rejections = Counter()
    manifests = []
    digest = sha256()
    ages = {"assumed_same_date_IST":[],"assumed_same_date_UTC":[]}
    ratio_bid,ratio_ask = [],[]
    with (output/f"normalized-{day}.jsonl").open("w",encoding="utf-8") as stream:
        for path in paths:
            stat = path.stat()
            parquet = pq.ParquetFile(path)
            required = {"received_at","security_id","exchange_segment","packet_json"}
            if not required.issubset(parquet.schema_arrow.names):
                raise ValueError("raw capture schema lacks venue/receipt/packet identity")
            columns = sorted(required | ({"capture_scope"} & set(parquet.schema_arrow.names)))
            file_digest = sha256(path.read_bytes()).hexdigest()
            manifests.append({"path":str(path.relative_to(ROOT)),"sha256":file_digest,
                              "bytes":stat.st_size,"rows":parquet.metadata.num_rows})
            row_number = 0
            for batch in parquet.iter_batches(batch_size=4096,columns=columns):
                for row in batch.to_pylist():
                    row_number += 1
                    try:
                        sid = int(row["security_id"])
                    except (ValueError,TypeError):
                        counts["unselectable_identity"] += 1
                        continue
                    if sid not in ids or row["exchange_segment"] != "NSE_EQ":
                        continue
                    counts["selected_packets"] += 1
                    scope = row.get("capture_scope") or "unknown"
                    counts[f"scope_{scope}"] += 1
                    digest.update(json.dumps(row,sort_keys=True,separators=(",",":"),default=str).encode())
                    try:
                        packet = normalizer.normalize_decoded_row(row)
                    except normalizer.NormalizationError as exc:
                        rejections[exc.code] += 1
                        counts["rejected_packets"] += 1
                    else:
                        counts["normalized_packets"] += 1
                        types[packet.packet_type] += 1
                        counts[f"trade_semantics_{packet.trade_time_semantics}"] += 1
                        counts["quote_event_time_unknown"] += packet.quote_event_utc_us is None
                        counts["top_bid_less_than_aggregate"] += packet.best_bid_quantity < packet.bid_quantity_5
                        counts["top_ask_less_than_aggregate"] += packet.best_ask_quantity < packet.ask_quantity_5
                        ratio_bid.append(packet.bid_quantity_5/packet.best_bid_quantity)
                        ratio_ask.append(packet.ask_quantity_5/packet.best_ask_quantity)
                        for label,basis in (("assumed_same_date_IST","Asia/Kolkata"),
                                            ("assumed_same_date_UTC","UTC")):
                            offset = normalizer.assumed_same_date_offset(packet,basis=basis)
                            if offset is not None:
                                ages[label].append(offset)
                                counts[f"{label}_negative"] += offset < 0
                                counts[f"{label}_over_5s"] += offset > 5
                        record = {**asdict(packet),"source_file":str(path.relative_to(ROOT)),
                                  "source_row_1based":row_number}
                        stream.write(json.dumps(record,separators=(",",":"),allow_nan=False)+"\n")
                    if counts["selected_packets"] >= limit:
                        break
                if counts["selected_packets"] >= limit:
                    break
            if path.stat().st_mtime_ns != stat.st_mtime_ns or path.stat().st_size != stat.st_size:
                raise RuntimeError("source changed during read-only audit")
            if counts["selected_packets"] >= limit:
                break
    quantiles = lambda values: {str(q):float(np.quantile(values,q)) for q in (.5,.95,.99)} if values else {}
    normalized_file = output/f"normalized-{day}.jsonl"
    return {"date":day,"sample_limit":limit,"sample_limit_reached":counts["selected_packets"]>=limit,
            "available_files":len(paths),"read_files":manifests,"counts":dict(counts),
            "rejections":dict(rejections),"normalized_types":dict(types),
            "sample_rows_sha256":digest.hexdigest(),
            "normalized_sha256":sha256(normalized_file.read_bytes()).hexdigest(),
            "sensitivity_offsets_seconds":{k:quantiles(v) for k,v in ages.items()},
            "aggregate_to_best_quantity_ratio":{"bid":quantiles(ratio_bid),"ask":quantiles(ratio_ask)},
            "sampling":"first selected NSE cash cohort packets in sorted file order",
            "promotion_eligible":False,"interpretation":"trade time arithmetic, not quote age or network latency"}


def main() -> None:
    folder = Path(__file__).resolve().parent
    output = folder/"runs/initial-v1"
    if output.exists():
        raise ValueError("use a new run directory, preserve prior evidence")
    universe_path = ROOT/"research/common/cache/universe.json"
    universe = json.loads(universe_path.read_text())
    if universe["source_date"] >= min(DATES):
        raise ValueError("cohort must predate every raw session")
    ids = {int(row["security_id"]) for row in universe["selected"]}
    output.mkdir(parents=True)
    source = output/"source"
    source.mkdir()
    hashes = {}
    for path in folder.glob("*.py"):
        content = path.read_bytes(); (source/path.name).write_bytes(content)
        hashes[path.name] = sha256(content).hexdigest()
    plan = {"dates":DATES,"limit_per_date":20000,"universe":universe,
            "universe_sha256":sha256(universe_path.read_bytes()).hexdigest(),
            "python":platform.python_version(),"source_hashes":hashes,
            "trade_clock_default":"date and timezone unknown for bare HH:MM:SS",
            "sensitivities":["same receipt date in IST","same receipt date in UTC"],
            "original_wire_in_archive":False,"live_or_broker_access":False}
    (output/"plan.json").write_text(json.dumps(plan,indent=2),encoding="utf-8")
    reports = [audit(day,ids,output) for day in DATES]
    (output/"audit.json").write_text(json.dumps(reports,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps([{k:r[k] for k in ("date","counts","rejections","sensitivity_offsets_seconds",
                                      "aggregate_to_best_quantity_ratio")} for r in reports],indent=2))


if __name__ == "__main__":
    main()
