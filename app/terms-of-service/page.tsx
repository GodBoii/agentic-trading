import { Clause, LegalShell } from '@/components/legal/legal-shell'

export const metadata = {
    title: 'Terms of service',
    description: 'Terms and conditions governing the use of the PolyCognition platform.',
}

/**
 * Content only. The frame, prose styling and footer come from `LegalShell`, which
 * this page shares with the privacy policy.
 */
export default function TermsOfServicePage() {
    return (
        <LegalShell
            title="Terms of service"
            updated="24 August 2026"
            sibling={{ href: '/privacy-policy', label: 'Privacy policy' }}
        >
            <Clause index={1} heading="Acceptance">
                <p>
                    Using the PolyCognition platform means agreeing to these terms. If you do not agree, stop using it.
                    We may change these terms; continuing to use the platform after a change is posted means accepting
                    the new version.
                </p>
            </Clause>

            <Clause index={2} heading="What the service is">
                <p>
                    PolyCognition provides AI trading agents that connect to your Dhan broker account, scan the NSE
                    universe, identify possible intraday setups, and place orders inside the risk parameters you define.
                    It is a software tool. It is not financial advice, portfolio management, or an investment
                    recommendation.
                </p>
            </Clause>

            <Clause index={3} heading="Eligibility">
                <ul>
                    <li>You are at least 18.</li>
                    <li>You are resident in India, or otherwise permitted to trade on Indian exchanges.</li>
                    <li>You hold a valid Dhan brokerage account in your own name.</li>
                    <li>No law or regulation prohibits you from using the service.</li>
                </ul>
            </Clause>

            <Clause index={4} heading="Your account and the broker connection">
                <p>
                    Keeping your account credentials confidential is your responsibility. Connecting a Dhan account
                    authorises PolyCognition to place orders, query positions and read market data on your behalf through
                    the Dhan API.
                </p>
                <p>
                    You can revoke that authorisation at any time, either from your Dhan account settings or by
                    disconnecting on the Portfolio screen. Revoking it stops all automated trading.
                </p>
            </Clause>

            <Clause index={5} heading="Trading risk">
                <p>
                    <strong>
                        Trading equities and derivatives carries a substantial risk of loss and is not suitable for every
                        investor.
                    </strong>
                </p>
                <ul>
                    <li>Past agent performance does not predict future results.</li>
                    <li>We do not guarantee profits, particular returns, or that losses will be avoided.</li>
                    <li>
                        Market conditions, execution latency, API outages and software faults can all produce trades that
                        differ from what was expected.
                    </li>
                    <li>
                        Every financial consequence of a trade placed through the platform is yours, whether you started
                        it or an agent did.
                    </li>
                    <li>
                        The service exists for research and education. Nothing on it is investment advice, a
                        recommendation, or a solicitation to buy or sell a security.
                    </li>
                </ul>
            </Clause>

            <Clause index={6} heading="Prohibited conduct">
                <p>You agree not to:</p>
                <ul>
                    <li>Use the service for anything illegal or in breach of SEBI regulations.</li>
                    <li>Attempt market manipulation, wash trading, or any other form of market abuse.</li>
                    <li>Reverse-engineer, decompile or extract the source of the agents or their algorithms.</li>
                    <li>Interfere with, disrupt or overload the service or its infrastructure.</li>
                    <li>Share your credentials or let anyone else use the service through your account.</li>
                    <li>Drive the service with scripts or bots outside the provided interface.</li>
                </ul>
            </Clause>

            <Clause index={7} heading="Intellectual property">
                <p>
                    The content, algorithms, models, code, design and branding of the platform belong to PolyCognition and
                    are protected by copyright, trademark and related law. You get a limited, non-exclusive,
                    non-transferable licence to use the service for your own trading.
                </p>
            </Clause>

            <Clause index={8} heading="Availability">
                <p>
                    We aim to keep the platform up during market hours but do not guarantee uninterrupted access.
                    Maintenance, upgrades, third-party outages including the Dhan API, data providers or cloud
                    infrastructure, and events outside our control can all take it offline. We are not liable for losses
                    caused by downtime.
                </p>
            </Clause>

            <Clause index={9} heading="Limitation of liability">
                <p>
                    So far as the law allows, PolyCognition and its officers, employees and affiliates are not liable for
                    indirect, incidental, special, consequential or punitive damages, including lost profits, trading
                    losses, lost data or business interruption, arising from your use of the service.
                </p>
                <p>
                    Total liability for any claim under these terms will not exceed what you paid PolyCognition in the
                    twelve months before the claim.
                </p>
            </Clause>

            <Clause index={10} heading="Indemnity">
                <p>
                    You agree to indemnify PolyCognition against claims, damages, losses and expenses, legal fees
                    included, arising from your use of the service, your breach of these terms, or your infringement of
                    someone else&apos;s rights.
                </p>
            </Clause>

            <Clause index={11} heading="Termination">
                <p>
                    We may suspend or end your access at any time, with or without cause or notice. Your right to use the
                    service ends immediately on termination. Open positions are not closed automatically when an account
                    ends, so managing your broker account directly remains your responsibility.
                </p>
            </Clause>

            <Clause index={12} heading="Governing law">
                <p>
                    Indian law governs these terms. Disputes fall under the exclusive jurisdiction of the courts of
                    Bangalore, Karnataka, India.
                </p>
            </Clause>

            <Clause index={13} heading="Severability">
                <p>
                    If any provision here is unenforceable, it is narrowed or removed only as far as necessary, and the
                    rest stays in force.
                </p>
            </Clause>

            <Clause index={14} heading="Contact">
                <p>
                    Questions about these terms go to <a href="mailto:legal@polycognition.com">legal@polycognition.com</a>
                    .
                </p>
            </Clause>
        </LegalShell>
    )
}
