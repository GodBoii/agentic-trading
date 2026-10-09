# Findings

Adding volume and stock-peer information produced small forecast changes, but did not beat the training-mean forecast in later-date squared error. These results hold the model, targets and observations fixed. They do not establish that the same information cannot help a different model or dataset.

| Horizon | Price/VWAP RMSE bps | Add own volume | Add peer context | Full context | Training-mean control |
|---|---:|---:|---:|---:|---:|
|5 minutes|18.7836|18.7836|18.7838|18.7835|18.7613|
|15 minutes|32.7471|32.7474|32.7419|32.7413|32.7036|
|30 minutes|46.0328|46.0374|46.0275|46.0257|45.9996|

All columns use the same96,747 evaluation rows across384 dates. At30 minutes, peer context modestly improved RMSE relative to price/VWAP alone, but still lost to the constant benchmark. Full-context raw direction accuracy was51.12% versus52.35% for training-mean direction. Correlated stocks/labels and this previously available history prevent row counts becoming independent evidence.

## Cost and account results

At2bps per leg plus fees, the30-minute price/VWAP rule took50 positions and lostRs7,134.46. Own-volume took80 and lostRs8,971.06. Peer context took88 and gainedRs804.36. Full context took81 and lostRs7,750.67. The small positive peer result became a loss ofRs502.98 over22 positions under5bps costs. It is a hypothesis that did not survive that sensitivity, not an established edge or reason to select its feature subset after observing test results.

At15 minutes, all four active feature versions lost betweenRs1,973.65 andRs4,239.15 at2bps. At5 minutes, each traded only once and lostRs602.43. Constant training-mean forecasts emitted no positions at any horizon. Full account ledgers and all sensitivities are retained.

Several higher-cost scenarios have smaller losses or positive totals. Increasing the assumed cost also raises the admission hurdle, changing the stocks/dates admitted. Those totals do not demonstrate that worse execution improves the same trades. The2bps and5bps populations must not be interpreted as an isolated fill-cost experiment.

## Verification and limits

Three focused tests pass for nested feature comparisons, saved coefficient reproduction and train-only scaler immutability. The separate verifier reconstructs every saved ridge forecast from immutable numeric parameters and reconciles all accounts, fees, delayed fill timing, non-overlapping stock positions and slot/capital limits.

Independent review identified two gaps in the initial verifier, although the existing evidence was complete. Version2 now requires all six prediction files and sixty account ledgers, compares frozen model/input fingerprints and reconciles saved result totals and RMSE with the row evidence. A corruption test confirms that missing prediction or trade files fail. The earlier verification report is preserved.

Peer residuals are linear combinations of own and peer returns. Adding redundant columns can also change the effective regularization under fixed ridge alpha. This comparison therefore cannot attribute every small change solely to new information.

The feature and account assumptions are shared with track45: current-survivor selection, conditional complete-session coverage, unknown candle timestamp/adjustment provenance, peer proxy rather than actual market/sector data, and candle-price execution without bid/ask capacity. Each account date starts fresh; totals do not compound or estimate annual returns. No production or live order setting changed.
