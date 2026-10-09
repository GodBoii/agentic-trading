# Research batch results

Results are offline historical diagnostics. The table lists every completed account-replay variant by track, with no sorting by profitability. Different strategy/account policies can change exposure and loss-halt timing, so totals alone do not measure forecast quality.

Receipt-proxy rows assume quote usability from recorded receipts. Source event age, exact queues, actual fills and decoder provenance are not established. Strict rows can be too sparse to estimate performance. No pristine final holdout exists in these dates.

Incomplete exposure is reported separately. Closed-trade P&L excludes remaining positions and is not the account's final outcome. The seven dates are development Aug19/20/21, validation Aug24/25, and historical audit Aug31/Sep1. Models that train on development evaluate only later dates.

## Account simulations

| Track | Variant | Mode | Sessions | Closed trades | Gross Rs | Fees Rs | Closed net Rs | Incomplete sessions |
|---|---|---|---:|---:|---:|---:|---:|---:|
|02_opening_range|orb15|recent_trade|7|0|0.00|0.00|0.00|0|
|02_opening_range|orb15|receipt_proxy|7|15|-363.73|1,235.80|-1,599.53|0|
|02_opening_range|orb30_direction|recent_trade|7|0|0.00|0.00|0.00|0|
|02_opening_range|orb30_direction|receipt_proxy|7|13|-755.72|1,074.47|-1,830.19|0|
|02_opening_range|orb15_vwap|recent_trade|7|0|0.00|0.00|0.00|0|
|02_opening_range|orb15_vwap|receipt_proxy|7|15|-363.73|1,235.80|-1,599.53|0|
|03_mean_reversion|rolling_zscore_fade|recent_trade|7|0|0.00|0.00|0.00|0|
|03_mean_reversion|rolling_zscore_fade|receipt_proxy|7|85|-2,773.67|6,472.64|-9,246.31|1|
|03_mean_reversion|vwap_deviation_turn|recent_trade|7|0|0.00|0.00|0.00|0|
|03_mean_reversion|vwap_deviation_turn|receipt_proxy|7|183|-4,054.82|13,648.95|-17,703.77|0|
|03_mean_reversion|ou_admissible_fade|recent_trade|7|0|0.00|0.00|0.00|0|
|03_mean_reversion|ou_admissible_fade|receipt_proxy|7|0|0.00|0.00|0.00|0|
|04_microstructure|imbalance_persistence|recent_trade|7|11|-510.86|874.91|-1,385.77|0|
|04_microstructure|imbalance_persistence|receipt_proxy|7|167|-5,919.57|11,958.11|-17,877.68|0|
|04_microstructure|depth_change|recent_trade|7|20|-619.32|1,568.04|-2,187.36|0|
|04_microstructure|depth_change|receipt_proxy|7|176|-6,196.78|12,129.68|-18,326.46|0|
|04_microstructure|weighted_quote_trend|recent_trade|7|6|-217.46|412.35|-629.81|0|
|04_microstructure|weighted_quote_trend|receipt_proxy|7|175|-6,444.01|11,525.78|-17,969.79|0|
|05_relative_value|peer_continuation|recent_trade|7|2|-725.63|165.33|-890.96|0|
|05_relative_value|peer_continuation|receipt_proxy|7|151|-6,389.37|11,426.20|-17,815.57|0|
|05_relative_value|peer_reversal|recent_trade|7|2|589.73|165.32|424.41|0|
|05_relative_value|peer_reversal|receipt_proxy|7|165|-5,275.65|12,466.26|-17,741.91|0|
|05_relative_value|peer_confirmed_reversal|recent_trade|7|1|55.80|82.66|-26.86|0|
|05_relative_value|peer_confirmed_reversal|receipt_proxy|7|178|-3,837.07|13,157.43|-16,994.50|0|
|06_volatility_compression|bollinger_relative|recent_trade|7|0|0.00|0.00|0.00|0|
|06_volatility_compression|bollinger_relative|receipt_proxy|7|1|-188.29|82.68|-270.97|0|
|06_volatility_compression|bollinger_absolute15|recent_trade|7|0|0.00|0.00|0.00|0|
|06_volatility_compression|bollinger_absolute15|receipt_proxy|7|46|-1,858.08|3,649.52|-5,507.60|0|
|06_volatility_compression|compressed_range5|recent_trade|7|1|-171.28|82.67|-253.95|0|
|06_volatility_compression|compressed_range5|receipt_proxy|7|138|-6,782.08|10,808.84|-17,590.92|0|
|07_indicator_patterns|rsi_recross|recent_trade|7|0|0.00|0.00|0.00|0|
|07_indicator_patterns|rsi_recross|receipt_proxy|7|141|-6,026.83|11,012.50|-17,039.33|0|
|07_indicator_patterns|bollinger_breakout|recent_trade|7|0|0.00|0.00|0.00|0|
|07_indicator_patterns|bollinger_breakout|receipt_proxy|7|156|-5,490.99|12,184.25|-17,675.24|0|
|07_indicator_patterns|wick_rejection|recent_trade|7|0|0.00|0.00|0.00|0|
|07_indicator_patterns|wick_rejection|receipt_proxy|7|26|-2,060.96|1,943.92|-4,004.88|1|
|08_statistical_models|ridge_net_2bps|recent_trade|4|0|0.00|0.00|0.00|0|
|08_statistical_models|ridge_net_2bps|receipt_proxy|4|0|0.00|0.00|0.00|0|
|08_statistical_models|logistic_probability_65|recent_trade|4|0|0.00|0.00|0.00|0|
|08_statistical_models|logistic_probability_65|receipt_proxy|4|0|0.00|0.00|0.00|0|
|08_statistical_models|ridge_net_5bps|recent_trade|4|0|0.00|0.00|0.00|0|
|08_statistical_models|ridge_net_5bps|receipt_proxy|4|0|0.00|0.00|0.00|0|
|09_variance_ratio|trend_q2|recent_trade|7|0|0.00|0.00|0.00|0|
|09_variance_ratio|trend_q2|receipt_proxy|7|63|-1,433.26|4,912.79|-6,346.05|0|
|09_variance_ratio|adaptive_q2|recent_trade|7|0|0.00|0.00|0.00|0|
|09_variance_ratio|adaptive_q2|receipt_proxy|7|133|-4,446.54|10,060.03|-14,506.57|0|
|09_variance_ratio|adaptive_q5|recent_trade|7|0|0.00|0.00|0.00|0|
|09_variance_ratio|adaptive_q5|receipt_proxy|7|179|-3,084.39|13,661.42|-16,745.81|0|
|10_vwap_pullback|vwap_reclaim|recent_trade|7|0|0.00|0.00|0.00|0|
|10_vwap_pullback|vwap_reclaim|receipt_proxy|7|1|-209.08|82.64|-291.72|0|
|10_vwap_pullback|vwap_bounded_pullback|recent_trade|7|0|0.00|0.00|0.00|0|
|10_vwap_pullback|vwap_bounded_pullback|receipt_proxy|7|4|43.78|251.28|-207.50|0|
|11_exit_math|fixed_30_15_300|recent_trade|7|2|-740.60|165.33|-905.93|0|
|11_exit_math|fixed_30_15_300|receipt_proxy|7|155|-5,944.02|11,698.51|-17,642.53|0|
|11_exit_math|double_distances_60_30_300|recent_trade|7|2|-740.60|165.33|-905.93|0|
|11_exit_math|double_distances_60_30_300|receipt_proxy|7|151|-6,390.68|11,486.27|-17,876.95|0|
|11_exit_math|short_time_30_15_60|recent_trade|7|2|-281.44|165.34|-446.78|0|
|11_exit_math|short_time_30_15_60|receipt_proxy|7|174|-4,889.65|13,055.14|-17,944.79|0|
|12_execution_costs|base_execution|recent_trade|7|2|-740.60|165.33|-905.93|0|
|12_execution_costs|base_execution|receipt_proxy|7|155|-5,944.02|11,698.51|-17,642.53|0|
|12_execution_costs|footprint_1pct|recent_trade|7|1|-9.17|7.36|-16.53|0|
|12_execution_costs|footprint_1pct|receipt_proxy|7|359|-3,851.47|12,958.60|-16,810.07|0|
|12_execution_costs|delay_3s_slippage_3bps|recent_trade|7|1|-220.15|82.67|-302.82|0|
|12_execution_costs|delay_3s_slippage_3bps|receipt_proxy|7|116|-9,043.05|8,778.14|-17,821.19|0|
|12_execution_costs|no_trade_control|recent_trade|7|0|0.00|0.00|0.00|0|
|12_execution_costs|no_trade_control|receipt_proxy|7|0|0.00|0.00|0.00|0|
|14_intraday_seasonality|same_slot_mean|recent_trade|4|0|0.00|0.00|0.00|0|
|14_intraday_seasonality|same_slot_mean|receipt_proxy|4|16|87.84|1,082.64|-994.80|0|
|14_intraday_seasonality|same_slot_unanimous_sign|recent_trade|4|0|0.00|0.00|0.00|0|
|14_intraday_seasonality|same_slot_unanimous_sign|receipt_proxy|4|3|551.82|247.91|303.91|0|
|16_relative_volume|continuation|recent_trade|4|0|0.00|0.00|0.00|0|
|16_relative_volume|continuation|receipt_proxy|4|70|-2,170.22|5,406.55|-7,576.77|0|
|16_relative_volume|climax_reversal|recent_trade|4|0|0.00|0.00|0.00|0|
|16_relative_volume|climax_reversal|receipt_proxy|4|10|-521.02|826.53|-1,347.55|0|
|17_regime_mixtures|mixture_trend_continuation|recent_trade|4|0|0.00|0.00|0.00|0|
|17_regime_mixtures|mixture_trend_continuation|receipt_proxy|4|92|-3,151.34|6,989.17|-10,140.51|0|
|17_regime_mixtures|mixture_low_efficiency_fade|recent_trade|4|0|0.00|0.00|0.00|0|
|17_regime_mixtures|mixture_low_efficiency_fade|receipt_proxy|4|0|0.00|0.00|0.00|0|

Current initial batches total 39 frozen variant specifications and 492 policy/session account replays. This excludes original baseline runs, exact repeats and non-account diagnostics.

## What the evidence says

The early momentum, indicator, snapshot-imbalance and peer-residual proxy experiments generally lose before fees. Fees add a substantial hurdle. A smaller monetary loss under a reduced order size or tighter opportunity gate is not proof of improved alpha.

The numerical ridge/logistic model abstains because predicted net opportunity does not pass its frozen entry rules. Strict training was insufficient. Abstention is a valid outcome and must not be relabeled a profitable model.

The unanimous same-time-of-day rule has only three filled trades, all SBI shorts, and one later audit loss. Its small positive total does not establish repeatability across instruments or market conditions. Pair diagnostics have insufficient strict coverage and a negative fitted hedge coefficient. No pair trades qualified.

The paired exit experiment holds baseline entries fixed and diagnoses exits independently of account feedback. Its results are counterfactual outcomes, not a feasible simultaneous portfolio. Different holding times can overlap positions and need a real account controller before implementation.

Track 15 treats bare archived last-trade times as ambiguous without original wire/decoder provenance. Attaching a receipt date and timezone without evidence can produce misleading apparent freshness. Last-trade time is also not a source quote-event timestamp.

The raw-packet audit also shows that an aggregate-depth footprint can exceed displayed best-level size. Current aggressive fills remain a price/size proxy, not a depth-sweep or queue simulator. The new normalizer preserves actual level quantities for the next execution-model study.

Relative-volume continuation and climax-reversal lose before fees and after them. Their three-day seasonal baseline is weak and strict data cannot fit it. Gaussian-mixture continuation loses; the low-efficiency fade abstains. Density responsibilities are not profit probabilities.

The separate volatility-forecast study compares three fixed methods on 12,004 identical next-minute outcomes per method. Small pooled metric differences change ordering across periods. A squared-return forecast ranking does not establish directional alpha or a tradeable volatility opportunity.

## Where to inspect evidence

[Research index](C:/Users/prajw/Downloads/Trader/research/README.md) links each track's method. Each track stores its findings and versioned runs. The machine registry is [registry.json](C:/Users/prajw/Downloads/Trader/research/program/registry.json).

The verification tool checks archived source/data fingerprints and accounting on completed common runs. Its test report and verified-run list are saved below `program/runs`. Successful verification establishes consistency of the experiment evidence, not correctness of market-access assumptions.

## Next gates

Preserve an independently selected cohort with full packets and timestamp/decoder provenance. Add actual top-level quantities, corporate-action and trading-status references, and disconnect/queue-quality events. Calibrate order timelines and fills under the approved execution scope before selecting a fast strategy.

Continue the 40-topic queue with distinct economic or mathematical mechanisms. Specify hypotheses before opening later data, report source differences when adapting a paper, track all trials, and require new independent sessions for a final evaluation. Repeated parameter searches on these seven dates will not create a valid holdout.

No production trading module, credential state or live order was changed by this batch.
