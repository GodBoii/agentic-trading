import Sentinel from '@/components/sentinel/sentinel'
import { createClient } from '@/lib/supabase/server'

export const metadata = {
    title: 'PolyCognition — AI Trading Agents for Indian Markets',
    description:
        'Connect your Dhan broker and let AI agents scan the NSE universe, surface intraday opportunities, and execute within your risk limits.',
}

/**
 * Reading the session here, on the server, is what lets the landing page render
 * the right calls to action on the first paint.
 *
 * It used to be discovered on the client: `Nav` and `Hero` each ran their own
 * `getSession()` effect with its own `onAuthStateChange` subscription, and
 * `FinalCta` and `Footer` never checked at all. So a signed-in visitor was
 * served "Get started" and "Sign in", watched two of the four spots flip a
 * moment later, and was left with two buttons at the bottom of the page
 * inviting them to create the account they already had.
 *
 * `getSession()` rather than `getUser()`: this decides a link label, nothing
 * more. Every private route is gated by `middleware.ts`, so a stale cookie
 * cannot expose anything — it can only mislabel a button, and the click still
 * lands on the right place. `getUser()` would add a Supabase round trip to
 * every render of the most-visited page in the app to buy nothing.
 *
 * The try/catch preserves the rule `middleware.ts` sets out explicitly: public
 * routes stay up when auth is down. Failing closed to the signed-out layout is
 * always safe, where an unhandled rejection here would take the whole marketing
 * page offline during an outage.
 */
async function readSignedIn(): Promise<boolean> {
    try {
        const supabase = await createClient()
        const { data } = await supabase.auth.getSession()
        return Boolean(data.session)
    } catch {
        return false
    }
}

export default async function HomePage() {
    return <Sentinel signedIn={await readSignedIn()} />
}
