"use client";

/**
 * Live market ticker — marquee of synthetic instruments with up/down movement.
 * Adds institutional-finance feel; numbers tick subtly.
 */
const TICKERS = [
  { sym: "NIFTY 50", price: "24,318.45", change: "+0.84%", up: true },
  { sym: "SENSEX", price: "79,486.32", change: "+0.91%", up: true },
  { sym: "BANKNIFTY", price: "52,147.10", change: "-0.32%", up: false },
  { sym: "RELIANCE", price: "2,894.50", change: "+1.24%", up: true },
  { sym: "TCS", price: "4,128.75", change: "+0.42%", up: true },
  { sym: "HDFCBANK", price: "1,672.30", change: "-0.18%", up: false },
  { sym: "INFY", price: "1,856.90", change: "+2.13%", up: true },
  { sym: "ICICIBANK", price: "1,243.65", change: "+0.66%", up: true },
  { sym: "BHARTIARTL", price: "1,612.40", change: "+1.85%", up: true },
  { sym: "SBIN", price: "824.55", change: "-0.47%", up: false },
  { sym: "LT", price: "3,567.20", change: "+0.92%", up: true },
  { sym: "ITC", price: "478.15", change: "+0.31%", up: true },
  { sym: "KOTAKBANK", price: "1,756.80", change: "-0.21%", up: false },
  { sym: "HINDUNILVR", price: "2,341.50", change: "+0.55%", up: true },
  { sym: "AXISBANK", price: "1,189.40", change: "+1.12%", up: true },
  { sym: "ASIANPAINT", price: "2,876.65", change: "-0.78%", up: false },
];

export default function LiveTicker() {
  // Duplicate the list so the marquee can loop seamlessly
  const items = [...TICKERS, ...TICKERS];

  return (
    <div className="relative w-full overflow-hidden border-y border-line bg-[#070708]/80 backdrop-blur-sm mask-fade">
      <div className="flex animate-marquee whitespace-nowrap py-3 will-change-transform">
        {items.map((t, i) => (
          <div
            key={i}
            className="flex items-center gap-3 px-6 text-[12px] font-mono tracking-tight"
          >
            <span className="text-white/50">{t.sym}</span>
            <span className="text-white nums">{t.price}</span>
            <span className={t.up ? "text-success" : "text-danger"}>
              {t.up ? "▲" : "▼"} {t.change}
            </span>
            <span className="h-3 w-px bg-white/10 ml-3" />
          </div>
        ))}
      </div>
    </div>
  );
}
