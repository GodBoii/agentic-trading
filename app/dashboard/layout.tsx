import type { ReactNode } from 'react'
import ProductHeader from '@/components/product-header'
import { AgentRunProvider } from '@/components/agent/agent-run-provider'
import { createClient } from '@/lib/supabase/server'

/**
 * Shared shell for Portfolio, Agent and Trades.
 *
 * The identity lookup happens here rather than in each page: `middleware.ts`
 * already blocks unauthenticated access to `/dashboard/*`, so the pages were
 * re-checking `auth.getUser()` on the client purely to read an email — which
 * cost a round trip and produced a full-page loading flash on every visit.
 *
 * One container width and one canvas colour for all three sections; previously
 * each page picked its own. The width matches the header's so the brand, the
 * nav rail and the content below all share a single left edge.
 */
export default async function DashboardLayout({ children }: { children: ReactNode }) {
    const supabase = await createClient()
    const {
        data: { user },
    } = await supabase.auth.getUser()

    return (
        <div className="product-shell min-h-[100dvh] bg-canvas text-ink-primary">
            {/* Keyboard users otherwise tab the brand, three nav links and the
                account menu on every route before reaching the data. */}
            <a href="#main" className="skip-link">
                Skip to content
            </a>
            <ProductHeader email={user?.email} />
            <AgentRunProvider>
                <main id="main" className="mx-auto max-w-[1320px] px-4 pb-20 pt-6 sm:px-6 sm:pt-8 lg:px-8">
                    {children}
                </main>
            </AgentRunProvider>
        </div>
    )
}
