from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService

config = PipelineConfig()
dhan = DhanService(config)

print("Fetching intraday history for 532477...")
resp = dhan.fetch_intraday_history(
    532477,
    days=5,
    interval=1,
    exchange_segment="BSE_EQ",
    instrument_candidates=["EQUITY"]
)
print("Response:", resp)
