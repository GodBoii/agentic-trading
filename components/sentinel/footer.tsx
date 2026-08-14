import Link from "next/link";
import BrandMark from "@/components/brand-mark";

/**
 * Footer — minimal, professional.
 *
 * Brand, a one-line description, real links only, and the required
 * disclaimer. No fake ticker streams, no giant wordmark.
 */
export default function Footer() {
  return (
    <footer className="border-t border-white/[0.05] bg-[#030303] px-5 py-12 sm:px-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
        <div className="max-w-sm">
          <div className="flex items-center gap-2.5">
            <BrandMark className="h-7 w-7" />
            <span className="font-grotesk text-sm font-semibold text-white">
              PolyCognition
            </span>
          </div>
          <p className="mt-3 text-[13px] leading-relaxed text-white/40">
            AI trading agents for Indian markets, connected to your Dhan
            broker.
          </p>
        </div>

        <nav className="flex gap-6 text-[13px]" aria-label="Footer">
          <Link href="/signup" className="text-white/45 transition-colors duration-300 hover:text-white">
            Get started
          </Link>
          <Link href="/login" className="text-white/45 transition-colors duration-300 hover:text-white">
            Sign in
          </Link>
          <Link href="/dashboard" className="text-white/45 transition-colors duration-300 hover:text-white">
            Dashboard
          </Link>
        </nav>
      </div>

      <div className="mx-auto mt-10 flex max-w-6xl flex-col gap-2 border-t border-white/[0.05] pt-6 sm:flex-row sm:items-center sm:justify-between">
        <span className="text-[12px] text-white/30">
          © 2026 PolyCognition
        </span>
        <span className="text-[12px] text-white/30">
          For research purposes only · Not investment advice
        </span>
      </div>
    </footer>
  );
}
