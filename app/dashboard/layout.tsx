import type { ReactNode } from 'react'
import ProductHeader from '@/components/product-header'
import { createClient } from '@/lib/supabase/server'

/**
 * Shared shell for Dashboard, Agent and Trades.
 *
 * The identity lookup happens here rather than in each page: `middleware.ts`
 * already blocks unauthenticated access to `/dashboard/*`, so the pages were
 * re-checking `auth.getUser()` on the client purely to read an email — which
 * cost a round trip and produced a full-page loading flash on every visit.
 *
 * One container width (1280px) and one canvas colour for all three sections;
 * previously each page picked its own.
 */
export default async function DashboardLayout({ children }: { children: ReactNode }) {
    const supabase = await createClient()
    const {
        data: { user },
    } = await supabase.auth.getUser()

    return (
        <div className="product-shell min-h-screen bg-canvas text-ink-primary">
            <ProductHeader email={user?.email} />
            <main className="mx-auto max-w-[1280px] px-5 pb-16 pt-7 sm:px-8 sm:pt-9">{children}</main>
        </div>
    )
}
