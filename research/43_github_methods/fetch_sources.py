"""Save pinned upstream files as inert text for review, never import them."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import Request, urlopen


SOURCES = (
    ("microsoft/qlib", "main", "qlib/contrib/data/loader.py"),
    ("QuantConnect/Lean", "master", "Indicators/KaufmanAdaptiveMovingAverage.cs"),
    ("baobach/mlfinpy", "main", "mlfinpy/filters/filters.py"),
    ("pykalman/pykalman", "main", "pykalman/standard.py"),
    ("AI4Finance-Foundation/FinRL", "master", "finrl/meta/env_stock_trading/env_stocktrading.py"),
    ("skforecast/skforecast", "main", "skforecast/recursive/_forecaster_recursive.py"),
    ("hudson-and-thames/mlfinlab", "master", "mlfinlab/filters/filters.py"),
)


def retrieve(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Trader-research-source-review"})
    with urlopen(request, timeout=40) as response:
        return response.read()


def main() -> None:
    output = Path(__file__).parent / "upstream"
    output.mkdir(exist_ok=False)
    records = []
    for repo, branch, path in SOURCES:
        commit = json.loads(retrieve(f"https://api.github.com/repos/{repo}/commits/{branch}"))["sha"]
        url = f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
        content = retrieve(url)
        filename = repo.replace("/", "__") + "__" + Path(path).name + ".txt"
        (output / filename).write_bytes(content)
        records.append({"repo": repo, "branch": branch, "commit": commit, "path": path,
                        "raw_url": url, "source_url": f"https://github.com/{repo}/blob/{commit}/{path}",
                        "sha256": sha256(content).hexdigest(), "bytes": len(content),
                        "saved_file": filename})
        print(json.dumps({"repo": repo, "commit": commit, "bytes": len(content)}), flush=True)
    (output / "manifest.json").write_text(json.dumps({
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "execution": "inert text only, no upstream installation or execution",
        "sources": records}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
