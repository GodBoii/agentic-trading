# September 9 session review

Open `report.html` for the portable, self-contained version. It works offline.
`index.html` also works when kept beside `styles.css`, `app.js` and `data.js`.

The site contains all 118 signalled stocks, 660 signals, 35 AI starts and 26
submitted-order audits. Select a stock, signal or trade to inspect its timeline.
The table can be filtered and downloaded as CSV.

This is a frozen report, not a live dashboard. The broker snapshot is dated in
the report. No orders can be submitted from this site.

`findings.md` contains the written analysis. The research scripts are
`pipeline.research.session_chart_export` and `pipeline.research.session_audit`.
Raw account evidence stays under the backend's ignored results directory.
