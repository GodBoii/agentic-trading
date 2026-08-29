import { Clause, LegalShell } from '@/components/legal/legal-shell'

export const metadata = {
    title: 'Privacy policy',
    description: 'How PolyCognition collects, uses, and protects your data.',
}

/**
 * The frame, prose styling and footer come from `LegalShell`. This file is the
 * content only, which is the point: the wording is what changes here, and it
 * should be editable without touching a single class name.
 */
export default function PrivacyPolicyPage() {
    return (
        <LegalShell
            title="Privacy policy"
            updated="24 August 2026"
            sibling={{ href: '/terms-of-service', label: 'Terms of service' }}
        >
            <Clause index={1} heading="Introduction">
                <p>
                    PolyCognition operates an AI trading agent platform for Indian equity markets. This policy explains
                    what we collect, why we collect it, how long we keep it, and what you can ask us to do with it.
                </p>
                <p>
                    Using the platform means accepting the practices described here. If you do not accept them, please
                    stop using it.
                </p>
            </Clause>

            <Clause index={2} heading="Information we collect">
                <h3>What you give us</h3>
                <ul>
                    <li>Account details: name, email address and password.</li>
                    <li>
                        Broker connection: when you link a Dhan trading account we receive an access token that lets our
                        agents operate inside that account. We never receive or store your Dhan password.
                    </li>
                    <li>The capital limit and risk parameters you configure.</li>
                    <li>Anything you send us directly, such as support email.</li>
                </ul>

                <h3>What we record automatically</h3>
                <ul>
                    <li>Usage: pages opened, features used, timestamps and session length.</li>
                    <li>Device: browser, operating system and screen size.</li>
                    <li>IP address and the approximate location it resolves to.</li>
                    <li>The full activity log our agents produce while acting on your behalf.</li>
                </ul>
            </Clause>

            <Clause index={3} heading="How we use it">
                <ul>
                    <li>To run the platform and its trading agents.</li>
                    <li>
                        To place orders through your connected Dhan account, within the parameters you have configured.
                    </li>
                    <li>To improve the scanning, signal and risk logic.</li>
                    <li>To send account notifications: order confirmations, alerts and system status.</li>
                    <li>To detect and stop fraud, unauthorised access and other security incidents.</li>
                    <li>To meet legal and regulatory obligations.</li>
                </ul>
            </Clause>

            <Clause index={4} heading="Sharing and third parties">
                <p>We do not sell personal information. We share data with:</p>
                <ul>
                    <li>
                        <strong>Dhan.</strong> Order instructions and account queries go to Dhan through their API,
                        because that is how a trade reaches the exchange.
                    </li>
                    <li>
                        <strong>Supabase.</strong> Authentication, the database and backend services run on
                        Supabase-hosted infrastructure, so your account record lives there.
                    </li>
                    <li>
                        <strong>Analytics.</strong> Anonymised usage data may be shared with analytics services.
                    </li>
                    <li>
                        <strong>Legal requests.</strong> We disclose information where a law, regulation, court order or
                        government request requires it.
                    </li>
                </ul>
            </Clause>

            <Clause index={5} heading="Security">
                <p>
                    Traffic is encrypted in transit with TLS, sensitive credentials are encrypted at rest, and access is
                    controlled by role. Broker access tokens are never exposed to client-side code.
                </p>
                <p>
                    No transmission or storage method is completely secure. We work to protect your data but cannot
                    guarantee it against every possible attack.
                </p>
            </Clause>

            <Clause index={6} heading="Cookies and local storage">
                <p>
                    We use cookies and browser storage for your authentication session and to remember preferences such
                    as your appearance setting. These are required for the platform to work. We use no third-party
                    advertising cookies.
                </p>
            </Clause>

            <Clause index={7} heading="Retention">
                <p>
                    Account data is kept while the account is active. Trading logs and activity history are kept for at
                    least five years to meet financial record-keeping requirements. You can ask us to delete your account
                    and its data, subject to those retention obligations.
                </p>
            </Clause>

            <Clause index={8} heading="Your rights">
                <p>Depending on where you live, you may be able to:</p>
                <ul>
                    <li>See the personal data we hold about you.</li>
                    <li>Have inaccurate data corrected.</li>
                    <li>Have your data deleted, within the retention limits above.</li>
                    <li>Object to or restrict some processing.</li>
                    <li>Withdraw consent where processing relies on it.</li>
                </ul>
            </Clause>

            <Clause index={9} heading="Age">
                <p>
                    PolyCognition is not for anyone under 18, and we do not knowingly collect data from minors. If you
                    believe a minor has given us personal data, contact us and we will delete it.
                </p>
            </Clause>

            <Clause index={10} heading="Changes">
                <p>
                    We may update this policy. Changes appear on this page with a new date at the top. Continuing to use
                    the platform after a change means accepting the revised policy.
                </p>
            </Clause>

            <Clause index={11} heading="Contact">
                <p>
                    Questions about this policy or our data practices go to{' '}
                    <a href="mailto:privacy@polycognition.com">privacy@polycognition.com</a>.
                </p>
            </Clause>
        </LegalShell>
    )
}
