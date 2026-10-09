# Nifty research programme assessment

Twelve studies are complete as of 2 October 2026. The initial ten studies finished on 1 October; subsequent independent reviews corrected three evidence-processing issues and added two distinct studies. The original experiment has its own folder. Three subagents worked in parallel with the primary agent, then took different topics and independent reviews. All code and outputs are inside nifty-research. No raw archive, Ubuntu service or live trading configuration was changed.

The clearest candidate for further work is nearby depth at a one-minute horizon. It is a forecast hypothesis, not a profitable option strategy. More familiar indicators, more book levels, mean-reversion-looking fits and tighter exits did not automatically improve outcomes. Missing execution evidence remains a substantial obstacle.

## What was actually tested

| Folder | Scope run | Assessment |
|---|---|---|
| [01 baseline](01_depth_forecast_baseline/artifacts/report.md) | Six forecast references/models and ten directional quote replay policies | All fitted models lose to zero-return RMSE; all replay policies net-negative |
| [02 order book](02_orderbook_horizons/artifacts/report.md) | 32 fitted configurations plus 8 references; 28 feature-addition comparisons | Nearby depth helps most at one minute; deep depth and observed OFI do not add convincing value |
| [03 volatility/premiums](03_volatility_premiums/report.md) | 30 variance comparisons; two quote-age settings; parity IV and fixed-contract straddles | Smoother estimates beat very short windows; uncertainty and quote consistency prevent a premium-edge claim |
| [04 option hedging](04_options_hedging/report.md) | 12 structures at three horizons, plus 15 separately synthetic hedge scenarios | Every always-enter structure loses after costs; wings reduce sampled risk and increase costs |
| [05 indicators](05_indicator_patterns/report.md) | Six fixed rules at three horizons | No rule clears the declared 18-test family correction |
| [06 dependence/search](06_dependence_and_selection/report.md) | Three paired forecast comparisons; date/nonoverlap sensitivity; four synthetic search sizes | No added feature passes the exploratory joint max-statistic test |
| [07 statistical regimes](07_statistical_regimes/report.md) | 13 methods at three horizons | Zero-return baseline has lowest pooled RMSE at every horizon |
| [08 exits](08_exit_policies/report.md) | Two directional structures, six exits and three horizons | Every net policy negative; stop effects change with horizon; missing quotes cause overshoot |
| [09 liquidity persistence](09_liquidity_persistence/artifacts/report.md) | 33 response trials and 54 exact-cohort control comparisons | Duration alone does not establish stronger prediction; four selected dates give weak inference |
| [10 execution](10_execution_sensitivity/report.md) | 24 quote replays at three extra-slippage settings | Every base-cost scenario negative; stale-quote assumptions do not create alpha |
| [11 forecast transfer](11_one_minute_option_transfer/report.md) | 18 one-minute option replay configurations | Ten active configurations lose after costs; eight abstain |
| [12 expiry mechanics](12_expiry_premium_mechanics/report.md) | Quote-shape, synchronisation and expiry-distance diagnostics | Sparse synchronized observations and conflicting date weights prevent a premium-edge claim |

These counts are deliberately not collapsed into one grand sample size. A model configuration, a paired hypothesis, a cost sensitivity and a synthetic hedge scenario are different units. The same market episodes recur in multiple studies. Within-study correction is not a programme-wide correction, and a few dated recordings cannot support a broad production conclusion.

## Nearby depth is a short-horizon hypothesis

Study 02's one-minute nearby-depth model has RMSE 1.4927 bps, versus 1.5340 for price-only and 1.5259 for zero return. Its equal-date improvement versus price-only is positive on all nine dates. The descriptive day-bootstrap MSE improvement interval is 0.0921 to 0.1380 bps squared.

The raw one-sided exact date-sign p-value is 1/512. Holm correction across 28 comparisons produces 0.0547. With only nine dates, 1/512 is the minimum possible raw p-value. Multiplying by 28 makes the first Holm threshold impossible to clear at 0.05, even with improvement on every date. This is limited statistical resolution, not proof that nearby depth has no information. It is also not permission to ignore correction.

The benefit weakens at three and five minutes and disappears at ten. Studies 01 and 02 differ slightly in their common feature cohorts, so their five-minute figures should not be presented as exact reruns of the same estimand.

The original frozen-near-depth hypothesis remains preserved. Its version-two export adds shared feature-code hashes and an explicit 2 October freeze date, with no coefficient changes. The exporter refuses to overwrite a prior freeze. Both disclose post-selection, require new dates, prohibit refitting during the proposed fixed thirty-session follow-up, and disable execution. Thirty sessions are a collection budget, not a statistical-power guarantee. The script does not turn on a collector.

## Volatility forecasting and premium valuation need separate evidence

Study 03 scores 2,749 horizon-labelled variance forecasts. At five minutes, EWMA 0.94 reduces pooled QLIKE from 0.7569 for the prior-date historical mean to 0.6234. Its equal-date improvement interval includes zero. Pooled losses and equal-date comparisons weight days differently and can disagree.

The parity analysis has 550 qualified IV observations across thirteen dates and median IV 9.792%. A common same-expiry forward interval fails at 2,215 of 2,766 eligible decisions. This is evidence of missing quote synchronisation or other model/data inconsistencies. It is not measured arbitrage.

Both long and short fixed-contract straddle observations have negative estimated mean net outcomes in all fifteen populated expiry/horizon subsets. These observations overlap and are conditional, not an executable portfolio. Calendar-time IV scaled into an intraday horizon is explicitly a mechanical proxy; it is not a measured volatility risk premium.

## Hedging changes risk and turnover

Study 04 has 7,199 priced records and 328 unresolved exits across configurations. All 36 always-enter structure/horizon configurations lose after estimated costs. The same market periods are reused, so this is not one account trading 7,199 independent times.

On 107 common priced fifteen-minute entries, an iron butterfly reduces the short straddle's worst sampled adverse P&L from approximately -INR 4,225 to -INR 1,368. The wings add approximately INR 139 estimated roundtrip costs per trade and worsen total net results on the paired subset. Sampled adverse excursion can miss worse losses between observations.

The separately synthetic delta-hedging experiment uses constant-volatility lognormal paths, fractional underlying units and generic proportional costs. It illustrates why hedge frequency trades tracking error against cost. It does not model Nifty jumps, integer futures lots, basis, margin or actual fills and is not counted as an empirical strategy success.

Short-option margin, fill sizes and atomic multi-leg execution remain unavailable. A bounded expiry payoff assumes all intended hedges are filled and maintained.

## Familiar rules and fitted regimes require falsification

RSI reversal, Bollinger reversal, EMA trend, prior Donchian breakout, opening-range breakout and five-minute reversal were implemented with fixed parameters. None clears the eighteen-test correction. The opening-range cohort is especially narrow because complete opening windows are scarce. Its result is not a general index opening-range estimate.

Study 07 compares autoregression, simple train-only Gaussian-mixture regimes, variance-ratio rules and OU-like rolling price fits. Zero-return RMSE is best at all three horizons. Approximately 96% of fitted short windows produce a coefficient between zero and one, with median apparent half-life about seven minutes, yet those forecasts do not improve prediction. A fitted restoring coefficient from a short window is not proof of stationarity or a tradable equilibrium.

The descriptive variance ratio is not reported as the full heteroskedasticity-corrected Lo-MacKinlay test. The mixture model is not Hamilton's Markov model, and the intraday HAR approximation is not Corsi's daily/weekly/monthly replication. Reports document the adaptations.

## Exit policies cannot manufacture an entry edge

Study 08 has 2,814 priced records, 120 unresolved exits and 273 records with incomplete monitoring. Every configuration is net-negative. A 10% debit stop and 20% target improves paired fifteen-minute single-option results by roughly INR 1,664, but worsens thirty-minute results by roughly INR 3,302. No threshold is selected as optimal.

The worst trailing overshoot is INR 416 after 110 missing five-second monitoring samples. Trigger thresholds are never substituted for fills; the replay reprices one second after the first observed trigger. The archive cannot tell when a continuous monitor would have reacted inside a recording gap.

Study 10 tests receipt-time quote ages of two/five seconds, latency of one/three/five seconds and extra slippage of 0.10/0.50/1.00 option points per transaction. All 24 base-cost configurations are net-negative. Quote age is not exchange quote age, and accepting older data cannot prove executable liquidity.

## Persistence did not validate the institutional-wall story

Study 09 streams four long sessions and reconstructs causal equal-second snapshots. It tests near-price quantities at fixed size thresholds and observed durations of ten, thirty and sixty seconds. Missing observations, recorder restarts and stale book sides reset persistence.

Conditional persistent-liquidity response is generally small. Matched-cohort comparisons are available against nearby imbalance, top-five imbalance and raw deep-wall counts. Raw means across different signal cohorts cannot rank methods fairly. Exact sign tests with only four dates have a minimum p-value of 1/16 even before correction; no positive significance claim is justified.

An aggregate quantity remaining at a price does not establish that the same orders remained. These data cannot identify banks, hidden institutional intent, spoofing, cancellations versus executions, or queue priority.

## Internet research and repo usage

The studies cite original papers and inspect primary public repos, including Stoikov's microprice research, `arch`, `py_vollib`, scikit-learn, statsmodels, QuantLib, Deep Hedging, `ta`, Backtesting.py, VectorBT and HftBacktest. Specific formulas and execution semantics were adapted into local implementations with tests. Full opaque trading repositories were not installed and run, and their advertised performance was not imported as evidence.

Each report distinguishes source motivation from a genuine replication. Synthetic price benchmarks, IV roundtrips, known-process simulations and causal invariance tests verify numerical behaviour. They do not establish Nifty profitability.

## Architecture changes justified by the programme

1. Forecast horizons must be explicit. A one-minute liquidity hypothesis cannot be passed to a thirty-minute strategy selector as the same evidence.
2. Physical movement forecasts and option-implied pricing belong in separate tools. Candidate net value must include spread, turnover and adverse-path risk.
3. Duration features require time weighting, gap resets and book-side freshness. Raw event counts are insufficient.
4. Stops need an observation-gap state and an actual liquidation policy. Unknown exposure halts later entries.
5. An agent receives exact contract candidates and missing-evidence fields, not invented margin, Greeks or expected profit.
6. Research promotion requires frozen fresh-date testing and economic validation. Selecting the best method among this programme's viewed results does not satisfy either.

No study is promoted to live trading. The next data requirements remain synchronous spot, option quote sizes and origin timestamps, IV/Greeks across expiries, event history, and prospective collector reliability. Those requirements explain what the current recordings can and cannot test; they do not replace the completed experiments.

## Reproduction and verification

From nifty-research, `python -m pytest -q` discovers the shared and study tests. `python run_program.py` runs every registered additional study with at most three concurrent scripts and records failures, durations and hashes. Individual run commands appear in each report. Study 01 uses `python -m nifty_lab evaluate`, `replay` and `report`.

The original baseline source snapshot matches all ten package hashes in its preserved provenance. Source archives remain in place. Derived caches, ledgers and large artifacts are locally ignored; study code and readable findings are available in their folders.

## Review corrections, 2 October 2026

Study 05's EMA and RSI now reset exponential histories after incomplete or missing minutes, rather than merely hiding signals for a warmup window. Opening-range signals require a complete current minute. All eighteen registered trials were rerun; none passes the declared correction. Prior results remain in the study's revision directory.

Study 07's daily MSE calculation now preserves the filtered scored-row index. The earlier pandas alignment lost or misassigned date contributions. Pooled forecast RMSE and prediction values are unchanged. The corrected fifteen-minute GMM2 equal-date improvement is -3.2791 bps squared, with a descriptive interval from -6.4315 to -0.5877. Earlier equal-date figures must not be used.

Study 10 validates delayed-entry expiry, strike and option type and rejects nonfinite signals. Its rerun results and ledger are unchanged byte for byte.

Study 09 now preserves packet time separately from reconstruction grid time and applies actual oldest-side freshness at the minute decision. Two complete bars are removed. Valid one/three/five-minute outcomes are now 1,362/1,344/1,326. Nearby-depth signed responses are now 0.2909/0.4262/0.4989 bps. All eighteen persistent-versus-near matched comparisons still favour simpler nearby depth. Cache reuse now checks content digests, audited source metadata and extraction dependencies; legacy-cache adoption is explicitly documented. Fifteen study tests pass.

## One-minute forecast transfer, 2 October 2026

[Study 11](11_one_minute_option_transfer/report.md) connects the short-horizon forecast hypothesis to a matching option holding period. Eighteen fixed configurations combine three forecast references, three thresholds and two structures. Contract selection happens at decision time; entry is one second later and the scheduled exit is sixty seconds after the decision, giving fifty-nine seconds of exposure.

Ten configurations trade and all lose after costs; eight learned-model configurations generate no trades. The nearby-depth single-option configuration at 0.5 bps has 152 priced trades, INR 87.75 gross, INR 9,577.59 estimated charges, and INR 11,465.84 net loss after additional slippage. Its debit-spread counterpart is also negative. No entered trade has an unresolved exit in this cohort.

This does not convert the selected forecast into a tradable edge. The one-minute source predictions were selected after looking at study 02, and their saved cohort excludes unavailable future underlying labels. The replay therefore remains a labelled-subset developmental comparison, not a complete prospective trading policy. It also lacks quote sizes and original exchange timestamps.

## Expiry mechanics and quote shapes, 2 October 2026

[Study 12](12_expiry_premium_mechanics/report.md) records 243,308 bid/ask quote-shape checks across receipt-skew and discount-rate sensitivities, 5,532 wing-IV attempts, 2,860 revalidations of fixed-contract straddle observations and 2,766 sampled minutes. These repeated checks are not independent trade opportunities.

The checks use the correct buying and selling sides for call/put monotonicity, discounted vertical caps and unequal-strike butterfly convexity. At zero assumed interest, tightening allowed receipt skew from two seconds to 0.25 seconds leaves one vertical-bound flag and no convexity flags. That remaining put vertical exceeds its fifty-point cap by 0.40 points, equivalent to INR 26 per assumed lot before costs. It lacks quote-origin timestamps, quantities, atomic fills and financing evidence. It is a data-quality observation, not demonstrated arbitrage.

Only two strict whole-slice wing-IV observations survive. Unequal distances and the five-strike neighbourhood also prevent interpreting those measurements as a stable fixed-delta risk reversal or full implied-volatility surface.

Expiry short-straddle means depend on weighting. The strict thirty-minute cohort contains nine overlapping observations on August 4 and two on August 11. Their within-date mean short net outcomes are approximately -INR 213.48 and +INR 508.76. Equal date weighting gives a positive mean, while pooled observation weighting remains negative. Neither is a portfolio or prospective-policy result. The dates have sharply different outcomes and the cohort is selected for known future prices.

Sampled activity tables retain short recording dates and separately show a minimum-sixty-minute-per-date sensitivity. No causal expiry effect, broader smile estimate or wing-hedging strategy is promoted.

## Verification status

The resumed subagents corrected study 07 date-index aggregation, study 09 packet-versus-grid freshness and study 10 delayed-entry identity checks. Root corrected study 05 exponential-history resets and made frozen exports immutable. Review notes and earlier outputs remain under each study's local revision directory. The original baseline still matches all recorded source-snapshot and artifact hashes.

Study 11's one-minute forecasts do not recover missing source predictions. Study 12's premium comparisons remain selected, overlapping diagnostics. These limits are retained rather than hidden by the additional experiments.
