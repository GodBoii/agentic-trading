from pipeline.config import PipelineConfig
from pipeline.services.nifty_depth_monitor import NiftyDepthMonitor


if __name__ == "__main__":
    print("NIFTY 50 MARKET DEPTH")
    NiftyDepthMonitor(PipelineConfig()).run()
