# Frozen hypotheses before initial runs

October 1, 2026. Parameters are specified before inspecting this track's real-data outcomes.

1. `bollinger_relative`: twenty observed minute closes, two population standard deviations, current BandWidth no larger than the minimum of 125 prior widths, ten-bar arming period, two consecutive outside-band closes plus common confirmation buffer.
2. `bollinger_absolute15`: same bands and confirmation but squeeze width at most fifteen basis points.
3. `compressed_range5`: prior five completed observed-close high/low channel width at most fifteen basis points, one completed breakout close beyond the common confirmation buffer.

Each uses the shared account, fees, execution delay, exits and risk parameters. No fitting or calibration from validation outcomes occurs. No source strategy's published profitability is being reproduced.

Fixed August 18 twelve-stock ADV universe. Development August 19, 20, 21; diagnostic validation August 24, 25; audit August 31 and September 1. All seven dates have prior project exposure. Run strict and separately labeled receipt-proxy modes. Retain negative and zero-entry outcomes. New thresholds require another hypothesis version and fresh independent data.
