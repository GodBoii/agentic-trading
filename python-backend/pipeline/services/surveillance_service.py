from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional, Set

import pandas as pd
import requests

from pipeline.config import PipelineConfig
from pipeline.services.storage_service import StorageService

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_GSM_URL = "https://www.bseindia.com/downloads1/List_of_GSM_Securities_{date}.CSV"
_ASM_URL = "https://www.bseindia.com/downloads1/Applicable_Beta_for_ASM_Framework.xlsx"


class SurveillanceService:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.root_dir = config.root_dir

    def _download_gsm_csv(self) -> Optional[Path]:
        today = datetime.now()
        for days_back in range(8):
            check_date = today - timedelta(days=days_back)
            date_str = check_date.strftime("%d%m%Y")
            url = _GSM_URL.format(date=date_str)
            try:
                print(f"Attempting to download GSM list for {check_date.strftime('%d-%m-%Y')}...", end=" ")
                response = requests.get(url, headers=_HEADERS, timeout=15)
                if response.status_code == 200 and len(response.content) > 100:
                    path = self.root_dir / f"List_of_GSM_Securities_{date_str}.CSV"
                    path.write_bytes(response.content)
                    print(f"Downloaded ({len(response.content)} bytes)")
                    return path
                print(f"Not found (HTTP {response.status_code})")
            except Exception as exc:
                print(f"Error: {str(exc)[:50]}")

        for name in sorted(self.root_dir.glob("List_of_GSM_Securities_*.CSV"), reverse=True):
            print(f"Using local GSM file: {name.name}")
            return name

        print("No GSM file found. Proceeding without GSM filter.")
        return None

    def _download_asm_xlsx(self) -> Optional[Path]:
        try:
            print("Downloading ASM framework list...", end=" ")
            response = requests.get(_ASM_URL, headers=_HEADERS, timeout=30)
            if response.status_code == 200 and len(response.content) > 100:
                path = self.root_dir / "Applicable_Beta_for_ASM_Framework.xlsx"
                path.write_bytes(response.content)
                print(f"Downloaded ({len(response.content)} bytes)")
                return path
            print(f"Failed (HTTP {response.status_code})")
        except Exception as exc:
            print(f"Error: {str(exc)[:50]}")

        candidate = self.root_dir / "Applicable_Beta_for_ASM_Framework.xlsx"
        if candidate.exists():
            print(f"Using local ASM file: {candidate.name}")
            return candidate

        print("No ASM file found. Proceeding without ASM filter.")
        return None

    def _load_security_ids_from_csv(self, path: Path, col_index: int = 1) -> Set[int]:
        ids: Set[int] = set()
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[1:]:
            parts = line.strip().split(",")
            if len(parts) > col_index:
                val = parts[col_index].strip().strip('"')
                if val.isdigit():
                    ids.add(int(val))
        return ids

    def _load_security_ids_from_xlsx(self, path: Path, col_name: str = "SCRIP_CODE") -> Set[int]:
        ids: Set[int] = set()
        try:
            df = pd.read_excel(path, engine="openpyxl")
            if col_name not in df.columns:
                print(f"Column '{col_name}' not found in XLSX. Columns: {list(df.columns)}")
                return ids
            for val in df[col_name].dropna():
                val_str = str(int(val) if isinstance(val, float) else val).strip()
                if val_str.isdigit():
                    ids.add(int(val_str))
        except Exception as exc:
            print(f"Error reading XLSX: {exc}")
        return ids

    def load_gsm_ids(self) -> Set[int]:
        gsm_path = self._download_gsm_csv()
        if gsm_path is None:
            return set()
        ids = self._load_security_ids_from_csv(gsm_path, col_index=1)
        print(f"Loaded {len(ids)} GSM security ids")
        return ids

    def load_asm_ids(self) -> Set[int]:
        # Applicable_Beta_for_ASM_Framework.xlsx is a beta-reference universe,
        # not the consolidated list of securities currently under ASM. Using
        # it as membership data incorrectly excludes most of the BSE universe.
        # Dhan's daily detailed master carries the current exchange-provided
        # ASM/GSM flag for each instrument.
        payload = StorageService.load_snapshot(self.config.bse_list_path) or {}
        ids: Set[int] = set()
        for stock in payload.get("stocks") or []:
            if str(stock.get("asm_gsm_flag") or "").strip().upper() != "Y":
                continue
            try:
                ids.add(int(stock["security_id"]))
            except (KeyError, TypeError, ValueError):
                continue
        print(f"Loaded {len(ids)} ASM/GSM-flagged security ids from Dhan master")
        return ids
