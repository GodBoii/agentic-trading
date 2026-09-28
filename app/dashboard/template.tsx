import type { ReactNode } from 'react'

/**
 * Remounts on every section change, which is what lets the incoming page play
 * a short entrance. Without it a tap on the tab bar swaps the whole screen in
 * one frame, and on a phone that reads as a reload rather than a move.
 */
export default function DashboardTemplate({ children }: { children: ReactNode }) {
    return <div className="route-enter">{children}</div>
}
