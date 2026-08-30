import re

with open('python-backend/pipeline/stages/intra_finder.py', 'r') as f:
    content = f.read()

# 1. Add Imports
imports = """
from pipeline.stages.live_state import LiveStockState, OHLCV
from pipeline.stages.activity_ranker import ActivityRanker
from pipeline.stages.setups.momentum import MomentumSetup
from pipeline.stages.setups.mean_reversion import MeanReversionSetup
"""
content = content.replace("from pipeline.stages.trade_readiness import evaluate_trade_readiness, fresh_indicator_events", imports)
content = content.replace("from pipeline.stages.indicator_event_engine import IndicatorEventEngine", "")

# 2. Update __init__
init_injection = """        self.activity_ranker = ActivityRanker(self.market_time)
        self.setups = {}
        self.last_rank_time = 0.0"""
content = re.sub(r'self\.indicator_engine = .*?\n\s*\)', init_injection, content, flags=re.DOTALL)

# 3. Rewrite _new_state
new_state = """    def _new_state(self, stock: Dict[str, Any]) -> LiveStockState:
        adv = float(stock.get("historical", {}).get("adv") or 0.0)
        atr = float(stock.get("historical", {}).get("atr") or 0.0)
        baselines = stock.get("intraday_baselines", {}).get("volumes", {})
        median_vols = {k: int(v) for k, v in baselines.items()}
        
        state = LiveStockState(
            security_id=int(stock["security_id"]),
            exchange_segment=stock["exchange_segment"],
            symbol=stock.get("symbol", ""),
            adv=adv,
            historical_atr=atr,
            median_time_volumes=median_vols,
            previous_close=float(stock.get("historical", {}).get("previous_close") or 0.0)
        )
        self.setups[state.security_id] = [MomentumSetup(), MeanReversionSetup()]
        return state"""
content = re.sub(r'def _new_state\(self, stock: Dict\[str, Any\]\) -> Dict\[str, Any\]:.*?\*\*IndicatorEventEngine\.state_fields\(\),\n        \}', new_state, content, flags=re.DOTALL)

# 4. Strip old IndicatorEventEngine usage from _state_checkpoint_fields
# Actually we can just let it be, but let's clean it.
checkpoint = """    @staticmethod
    def _state_checkpoint_fields() -> Tuple[str, ...]:
        return ()"""
content = re.sub(r'@staticmethod\n    def _state_checkpoint_fields\(\) -> Tuple\[str, \.\.\.\]:.*?pending_indicator_generation",\n        \)', checkpoint, content, flags=re.DOTALL)

# 5. Rewrite process_packet
process_packet_new = """    def process_packet(
        self,
        packet: Dict[str, Any],
        *,
        received_at: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        received_at = received_at or self.market_time.now()
        try:
            security_id = int(packet.get("security_id"))
        except (TypeError, ValueError):
            return None
        stock = self.stocks_by_security_id.get(security_id)
        state = self.states.get(security_id)
        price = self._number(packet, "LTP", "ltp", "last_price", "latest_traded_price")
        if not stock or state is None:
            return None
            
        self.packet_count += 1
        self.last_global_packet_at = received_at
        
        if price is None or price <= 0:
            return None

        # Update state
        volume = self._number(packet, "volume", "total_volume") or 0.0
        state.latest_price = price
        state.cumulative_volume = int(volume)
        state.update_session_extremes(price)
        
        official_vwap = self._number(packet, "avg_price", "average_price", "ATP")
        if official_vwap and official_vwap > 0:
            state.session_vwap = official_vwap
            
        # Update rolling ranges placeholder logic
        state.rolling_1m_high = max(state.rolling_1m_high, price) if state.rolling_1m_high else price
        state.rolling_1m_low = min(state.rolling_1m_low, price) if state.rolling_1m_low else price
        state.rolling_5m_high = max(state.rolling_5m_high, price) if state.rolling_5m_high else price
        state.rolling_5m_low = min(state.rolling_5m_low, price) if state.rolling_5m_low else price

        # Process ranking every 5 seconds
        now_ts = received_at.timestamp()
        if now_ts - self.last_rank_time >= 5.0:
            self.activity_ranker.rank(self.states)
            self.last_rank_time = now_ts

        # Run setup machines if stock is hot
        if state.is_hot:
            for setup in self.setups.get(state.security_id, []):
                setup.evaluate(state)
                if setup.state.name == "TRIGGERED" and not getattr(setup, "dispatched", False):
                    # Valid setup triggered!
                    depth = self._depth(packet)
                    direction_hint = setup.direction
                    slippage = self._estimated_slippage(depth, direction_hint, price, price)
                    
                    if slippage <= 0.002: # 0.20% slippage gate
                        contract = setup.to_contract(state)
                        contract["isin"] = stock["isin"]
                        contract["security_id"] = state.security_id
                        contract["symbol"] = state.symbol
                        contract["exchange_segment"] = state.exchange_segment
                        contract["market_date"] = self.market_time.market_date_str()
                        setup.dispatched = True
                        self._post_agent_event(contract)
                        return contract

        self._flush_if_due()
        self._save_status_if_due()
        return None"""
content = re.sub(r'def process_packet\([^)]+\) -> Optional\[Dict\[str, Any\]\]:.*?return emitted\[-1\] if emitted else None', process_packet_new, content, flags=re.DOTALL)


with open('python-backend/pipeline/stages/intra_finder.py', 'w') as f:
    f.write(content)
print("Applied refactor_methods.py")
