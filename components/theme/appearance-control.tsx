'use client'

import { Contrast, Moon, Sun } from '@/components/ui/icons'
import { SegmentedChoice, type TabItem } from '@/components/ui/tabs'
import { useTheme } from './theme-provider'
import type { ThemeChoice } from './theme-bootstrap'

const CHOICES: TabItem<ThemeChoice>[] = [
    { id: 'system', label: 'System', icon: <Contrast size={13} /> },
    { id: 'light', label: 'Light', icon: <Sun size={13} /> },
    { id: 'dark', label: 'Dark', icon: <Moon size={13} /> },
]

/**
 * Appearance, as a three-option setting rather than a switch.
 *
 * A sun/moon toggle is the default choice everywhere and it is wrong here for a
 * concrete reason, not an aesthetic one: it cannot express following the OS. A
 * switch has two positions, the preference has three, so the most useful state
 * — "match my system, including when it changes at sunset" — is unreachable and
 * the control silently pins whichever theme the user happened to land on.
 *
 * It is also a setting the user commits, not a view they browse, which is why
 * this is `SegmentedChoice` (a radio group) and not `SegmentedTabs`. Assistive
 * tech is told "pick one of these values", which is what this is.
 *
 * Motion comes free from that control: the pill travels between options
 * (recipe 16), and the travel is the whole feedback for an arrow-key change.
 * Nothing else animates here — the theme swap itself is a 150ms colour fade
 * owned by the stylesheet.
 */
export function AppearanceControl({ labelledBy }: { labelledBy: string }) {
    const { choice, setChoice } = useTheme()

    return (
        <SegmentedChoice
            items={CHOICES}
            value={choice}
            onChange={setChoice}
            ariaLabelledBy={labelledBy}
            className="t-tabs-fill"
        />
    )
}
