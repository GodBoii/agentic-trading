from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Set

import requests

from pipeline.config import PipelineConfig


class SurveillanceService:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.root_dir = config.root_dir

    def _download_csv(self, url_builder, file_builder, label: str) -> Optional[Path]:
        today = datetime.now()
        for days_back in range(8):
            check_date = today - timedelta(days=days_back)
            date_str = check_date.strftime("%d%m%Y")
            url = url_builder(date_str)
            try:
                print(f"Attempting to download {label} for {check_date.strftime('%d-%m-%Y')}...", end=" ")
                response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if response.status_code == 200:
                    path = self.root_dir / file_builder(date_str)
                    path.write_text(response.text, encoding="utf-8")
                    print("Downloaded")
                    return path
                print(f"Not found (HTTP {response.status_code})")
            except Exception as exc:
                print(f"Error: {str(exc)[:50]}")
        print(f"Could not download {label}")
        return None

    def _load_security_ids_from_csv(self, path: Path) -> Set[int]:
        ids: Set[int] = set()
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[1:]:
            parts = line.strip().split(",")
            if len(parts) >= 2 and parts[1].strip().isdigit():
                ids.add(int(parts[1].strip()))
        return ids

    def load_gsm_ids(self) -> Set[int]:
        downloaded = self._download_csv(
            lambda date_str: f"https://www.bseindia.com/downloads1/List_of_GSM_Securities_{date_str}.CSV",
            lambda date_str: f"List_of_GSM_Securities_{date_str}.CSV",
            "GSM list",
        )
        gsm_path = downloaded
        if gsm_path is None:
            for name in ["List_of_GSM_Securities_06042026.CSV", "List_of_GSM_Securities_23032026.CSV"]:
                candidate = self.root_dir / name
                if candidate.exists():
                    gsm_path = candidate
                    print(f"Found local GSM file: {candidate.name}")
                    break
        if gsm_path is None:
            print("No GSM file found. Proceeding without GSM filter.")
            return set()
        ids = self._load_security_ids_from_csv(gsm_path)
        print(f"Loaded {len(ids)} GSM security ids")
        return ids

    def load_asm_ids(self) -> Set[int]:
        paths: List[Path] = []
        long_term = self._download_csv(
            lambda date_str: f"https://www.bseindia.com/downloads1/List_of_Long_Term_ASM_Securities_{date_str}.CSV",
            lambda date_str: f"List_of_Long_Term_ASM_Securities_{date_str}.CSV",
            "Long_Term ASM",
        )
        short_term = self._download_csv(
            lambda date_str: f"https://www.bseindia.com/downloads1/List_of_Short_Term_ASM_Securities_{date_str}.CSV",
            lambda date_str: f"List_of_Short_Term_ASM_Securities_{date_str}.CSV",
            "Short_Term ASM",
        )
        if long_term:
            paths.append(long_term)
        if short_term:
            paths.append(short_term)

        if not paths:
            for name in [
                "List_of_Long_Term_ASM_Securities_06042026.CSV",
                "List_of_Long_Term_ASM_Securities_23032026.CSV",
                "List_of_Short_Term_ASM_Securities_06042026.CSV",
                "List_of_Short_Term_ASM_Securities_23032026.CSV",
            ]:
                candidate = self.root_dir / name
                if candidate.exists():
                    paths.append(candidate)
                    print(f"Found local ASM file: {candidate.name}")

        if not paths:
            print("No ASM files found. Proceeding without ASM filter.")
            return set()

        asm_ids: Set[int] = set()
        for path in paths:
            try:
                asm_ids.update(self._load_security_ids_from_csv(path))
            except Exception as exc:
                print(f"Error loading ASM file {path.name}: {exc}")

        print(f"Loaded {len(asm_ids)} ASM security ids")
        return asm_ids
