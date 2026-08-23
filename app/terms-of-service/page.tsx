import Link from 'next/link'
import BrandMark from '@/components/brand-mark'

export const metadata = {
    title: 'Terms of Service — PolyCognition',
    description: 'Terms and conditions governing the use of the PolyCognition platform.',
}

export default function TermsOfServicePage() {
    return (
        <div className="min-h-screen bg-[#030303] text-[#F8F8F8] antialiased">
            {/* Minimal header */}
            <header className="border-b border-white/[0.05] px-5 py-5 sm:px-8">
                <div className="mx-auto flex max-w-4xl items-center gap-2.5">
                    <Link href="/" className="flex items-center gap-2.5 transition-opacity hover:opacity-80">
                        <BrandMark className="h-7 w-7" />
                        <span className="font-grotesk text-sm font-semibold text-white">PolyCognition</span>
                    </Link>
                </div>
            </header>

            <main className="mx-auto max-w-4xl px-5 py-16 sm:px-8 sm:py-24">
                <h1 className="font-grotesk text-3xl font-bold tracking-tight text-white sm:text-4xl">
                    Terms of Service
                </h1>
                <p className="mt-3 text-sm text-white/40">Last updated: August 24, 2026</p>

                <div className="mt-12 space-y-10 text-[15px] leading-relaxed text-white/60">
                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">1. Acceptance of Terms</h2>
                        <p>
                            By accessing or using the PolyCognition platform (&ldquo;Service&rdquo;), you agree to be bound by
                            these Terms of Service (&ldquo;Terms&rdquo;). If you do not agree, you must stop using the Service
                            immediately. We reserve the right to modify these Terms at any time; continued use after
                            changes are posted constitutes acceptance.
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">2. Description of Service</h2>
                        <p>
                            PolyCognition provides AI-powered trading agents that connect to your Dhan broker account to
                            scan the NSE universe, identify potential intraday trading opportunities, and execute trades
                            within risk parameters you define. The Service is a software tool — it does not provide
                            financial advice, portfolio management, or investment recommendations.
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">3. Eligibility</h2>
                        <ul className="list-disc space-y-2 pl-5">
                            <li>You must be at least 18 years of age.</li>
                            <li>You must be a resident of India or otherwise legally permitted to trade on Indian stock exchanges.</li>
                            <li>You must hold a valid Dhan brokerage account in your own name.</li>
                            <li>You must not be prohibited from using the Service under any applicable law or regulation.</li>
                        </ul>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">4. Account and Broker Connection</h2>
                        <p>
                            You are responsible for maintaining the confidentiality of your account credentials. When you
                            connect your Dhan broker account, you authorize PolyCognition to place trades, query
                            positions, and access market data on your behalf via the Dhan API.
                        </p>
                        <p className="mt-3">
                            You may revoke this connection at any time through your Dhan account settings or by
                            disconnecting within the PolyCognition dashboard. Revoking access will stop all automated
                            trading activity.
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">5. Trading Risks and Disclaimers</h2>
                        <p className="font-semibold text-white/80">
                            Trading in equities and derivatives involves substantial risk of loss and is not suitable for
                            every investor.
                        </p>
                        <ul className="mt-3 list-disc space-y-2 pl-5">
                            <li>Past performance of AI agents does not guarantee future results.</li>
                            <li>PolyCognition does not guarantee profits, specific returns, or the avoidance of losses.</li>
                            <li>Market conditions, execution latency, API outages, and system errors can result in trades that differ from expected behavior.</li>
                            <li>You are solely responsible for all financial consequences of trades executed through the platform, whether initiated manually or by AI agents.</li>
                            <li>The Service is provided for research and educational purposes. Nothing on this platform constitutes investment advice, a recommendation, or a solicitation to buy or sell any security.</li>
                        </ul>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">6. Prohibited Conduct</h2>
                        <p>You agree not to:</p>
                        <ul className="mt-3 list-disc space-y-2 pl-5">
                            <li>Use the Service for any illegal purpose or in violation of SEBI regulations.</li>
                            <li>Attempt to manipulate markets, engage in wash trading, or use the platform for any form of market abuse.</li>
                            <li>Reverse-engineer, decompile, or attempt to extract the source code of the AI agents or proprietary algorithms.</li>
                            <li>Interfere with, disrupt, or overload the Service or its infrastructure.</li>
                            <li>Share your account credentials or allow others to access the Service through your account.</li>
                            <li>Use automated scripts or bots to interact with the Service outside of the provided interface.</li>
                        </ul>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">7. Intellectual Property</h2>
                        <p>
                            All content, algorithms, models, code, design, and branding on the PolyCognition platform are
                            the intellectual property of PolyCognition and are protected by applicable copyright,
                            trademark, and other intellectual property laws. You are granted a limited, non-exclusive,
                            non-transferable license to use the Service for personal, non-commercial trading purposes.
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">8. Service Availability</h2>
                        <p>
                            We aim to keep the platform available during market hours, but we do not guarantee
                            uninterrupted access. The Service may be unavailable due to maintenance, upgrades, third-party
                            outages (including Dhan API, data providers, or cloud infrastructure), or events beyond our
                            control. We are not liable for any losses resulting from downtime or unavailability.
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">9. Limitation of Liability</h2>
                        <p>
                            To the maximum extent permitted by law, PolyCognition and its officers, employees, and
                            affiliates shall not be liable for any indirect, incidental, special, consequential, or
                            punitive damages, including but not limited to loss of profits, trading losses, data loss,
                            or business interruption, arising out of or in connection with your use of the Service.
                        </p>
                        <p className="mt-3">
                            Our total liability for any claim arising from these Terms or the Service shall not exceed
                            the amount you paid to PolyCognition in the twelve months preceding the claim.
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">10. Indemnification</h2>
                        <p>
                            You agree to indemnify and hold harmless PolyCognition from any claims, damages, losses, or
                            expenses (including legal fees) arising from your use of the Service, your violation of these
                            Terms, or your violation of any third-party rights.
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">11. Termination</h2>
                        <p>
                            We may suspend or terminate your access to the Service at any time, with or without cause,
                            and with or without notice. Upon termination, your right to use the Service ceases
                            immediately. Any open positions managed by AI agents will not be automatically closed upon
                            account termination — you are responsible for managing your broker account directly.
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">12. Governing Law and Disputes</h2>
                        <p>
                            These Terms are governed by the laws of India. Any disputes arising from these Terms or the
                            Service shall be subject to the exclusive jurisdiction of the courts in Bangalore, Karnataka,
                            India.
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">13. Severability</h2>
                        <p>
                            If any provision of these Terms is found to be unenforceable or invalid, that provision shall
                            be limited or eliminated to the minimum extent necessary, and the remaining provisions shall
                            remain in full force and effect.
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-4 font-grotesk text-lg font-semibold text-white/90">14. Contact</h2>
                        <p>
                            For questions about these Terms of Service, contact us at:
                        </p>
                        <p className="mt-3 text-white/80">
                            Email: legal@polycognition.com
                        </p>
                    </section>
                </div>
            </main>

            {/* Minimal footer */}
            <footer className="border-t border-white/[0.05] bg-[#030303] px-5 py-8 sm:px-8">
                <div className="mx-auto flex max-w-4xl items-center justify-between text-[12px] text-white/30">
                    <span>© 2026 PolyCognition</span>
                    <div className="flex gap-4">
                        <Link href="/privacy-policy" className="transition-colors hover:text-white/60">Privacy Policy</Link>
                        <Link href="/" className="transition-colors hover:text-white/60">Home</Link>
                    </div>
                </div>
            </footer>
        </div>
    )
}
