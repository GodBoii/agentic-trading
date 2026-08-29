import type { SVGProps } from 'react'

/**
 * The project's icon set.
 *
 * Hand-drawn rather than imported. Lucide and Feather are the reflex choice and
 * they look like the reflex choice; more practically, this app needs about two
 * dozen glyphs and pulling a package for that costs a dependency and gives up
 * control of the one thing that has to be consistent — optical weight against
 * 11px to 13px type.
 *
 * House rules, so a new glyph cannot drift:
 *
 *   24x24 viewBox, 1.75 stroke, round caps and joins, `currentColor`.
 *   Geometry sits on whole or half pixels of the 24 grid.
 *   Metaphors stay literal. No rocket for "launch", no shield for "security" —
 *   the skill flags both, and they read as stock decoration rather than as a
 *   description of what the control does.
 *
 * Two animated glyphs live with their recipe instead of here, because each
 * needs geometry the recipe transforms: the disclosure chevron in
 * `components/motion/accordion.tsx` (symmetric about the viewBox centre, so it
 * can flip vertically) and the hover-opening arrow in
 * `components/motion/learn-more.tsx` (two arms sharing a transform origin).
 */
type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function Icon({ size = 16, children, ...rest }: IconProps) {
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.75}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
            focusable="false"
            {...rest}
        >
            {children}
        </svg>
    )
}

/* ── Direction ─────────────────────────────────────────────────────── */

export const ArrowRight = (props: IconProps) => (
    <Icon {...props}>
        <path d="M5 12h14M13 6l6 6-6 6" />
    </Icon>
)

export const ArrowLeft = (props: IconProps) => (
    <Icon {...props}>
        <path d="M19 12H5M11 18l-6-6 6-6" />
    </Icon>
)

export const ChevronDown = (props: IconProps) => (
    <Icon {...props}>
        <path d="M6 9l6 6 6-6" />
    </Icon>
)

export const ChevronRight = (props: IconProps) => (
    <Icon {...props}>
        <path d="M9 6l6 6-6 6" />
    </Icon>
)

/** Vertical carat pair, for a control that opens a menu either way. */
export const ChevronUpDown = (props: IconProps) => (
    <Icon {...props}>
        <path d="M8 10l4-4 4 4M8 14l4 4 4-4" />
    </Icon>
)

/* ── Actions ───────────────────────────────────────────────────────── */

export const Refresh = (props: IconProps) => (
    <Icon {...props}>
        <path d="M20 11a8 8 0 1 0-2.3 5.7" />
        <path d="M20 5v6h-6" />
    </Icon>
)

/** Dismiss. Pairs with `Plus` in an icon swap for open/close triggers. */
export const Close = (props: IconProps) => (
    <Icon {...props}>
        <path d="M6 6l12 12M18 6L6 18" />
    </Icon>
)

export const Plus = (props: IconProps) => (
    <Icon {...props}>
        <path d="M12 5v14M5 12h14" />
    </Icon>
)

export const Check = (props: IconProps) => (
    <Icon {...props}>
        <path d="M4.5 12.5l5 5 10-11" />
    </Icon>
)

export const Search = (props: IconProps) => (
    <Icon {...props}>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="M15.4 15.4L20 20" />
    </Icon>
)

export const External = (props: IconProps) => (
    <Icon {...props}>
        <path d="M14 4h6v6M20 4l-8.5 8.5" />
        <path d="M19 14v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </Icon>
)

/** Sign-out. Door with an outbound arrow, not a power symbol. */
export const SignOut = (props: IconProps) => (
    <Icon {...props}>
        <path d="M15 4h3a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-3" />
        <path d="M10 8l-4 4 4 4M6 12h9" />
    </Icon>
)

/* ── Sections ──────────────────────────────────────────────────────── */

/**
 * Portfolio. Stacked bars of unequal height read as holdings far more
 * directly than a briefcase or a pie chart does.
 */
export const Portfolio = (props: IconProps) => (
    <Icon {...props}>
        <path d="M4 20h16" />
        <path d="M7 20v-6M12 20V7M17 20v-9" />
    </Icon>
)

/**
 * The agent. A node with three outbound links: what the scanner, the signal
 * engine and the executor actually form. Deliberately not a robot face.
 */
export const Agent = (props: IconProps) => (
    <Icon {...props}>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 9V4M15 14l3.5 3.5M9 14l-3.5 3.5" />
        <circle cx="12" cy="3" r="1.15" />
        <circle cx="19.4" cy="18.4" r="1.15" />
        <circle cx="4.6" cy="18.4" r="1.15" />
    </Icon>
)

/** Trade history. A clock hand swept backwards over a dial. */
export const History = (props: IconProps) => (
    <Icon {...props}>
        <path d="M4 12a8 8 0 1 0 3-6.2" />
        <path d="M4 4v4h4" />
        <path d="M12 8.5V12l2.5 2" />
    </Icon>
)

/* ── State and meaning ─────────────────────────────────────────────── */

export const Alert = (props: IconProps) => (
    <Icon {...props}>
        <path d="M12 9v4M12 17h.01" />
        <path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
    </Icon>
)

export const Info = (props: IconProps) => (
    <Icon {...props}>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 11v5M12 8h.01" />
    </Icon>
)

/** Live activity. Reads as "a signal is arriving". */
export const Activity = (props: IconProps) => (
    <Icon {...props}>
        <path d="M3 12h3.5l2.5-7 3 14 2.5-7H21" />
    </Icon>
)

export const Document = (props: IconProps) => (
    <Icon {...props}>
        <path d="M14 3v5h5" />
        <path d="M19 8v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h8Z" />
        <path d="M9 13h6M9 17h4" />
    </Icon>
)

/** Link / connect, for the broker connection surface. */
export const Link = (props: IconProps) => (
    <Icon {...props}>
        <path d="M9.5 14.5 14.5 9.5" />
        <path d="M12.5 7.5l1.4-1.4a3.5 3.5 0 1 1 5 5L17.5 12.5" />
        <path d="M11.5 16.5l-1.4 1.4a3.5 3.5 0 1 1-5-5L6.5 11.5" />
    </Icon>
)

/* ── Capital and risk ──────────────────────────────────────────────── */

/**
 * Capital allocation. A balance beam: what "how much may one trade use" is,
 * and it avoids the money-bag cliche.
 */
export const Scales = (props: IconProps) => (
    <Icon {...props}>
        <path d="M12 4v16M8 20h8" />
        <path d="M5 8h14" />
        <path d="M5 8l-2.5 5a2.8 2.8 0 0 0 5 0Z" />
        <path d="M19 8l-2.5 5a2.8 2.8 0 0 0 5 0Z" />
    </Icon>
)

/** Adjust. Three tracks with offset handles, the standard settings metaphor. */
export const Sliders = (props: IconProps) => (
    <Icon {...props}>
        <path d="M4 7h16M4 12h16M4 17h16" />
        <circle cx="9" cy="7" r="1.9" fill="currentColor" stroke="none" />
        <circle cx="15.5" cy="12" r="1.9" fill="currentColor" stroke="none" />
        <circle cx="7.5" cy="17" r="1.9" fill="currentColor" stroke="none" />
    </Icon>
)

/** Available funds. */
export const Wallet = (props: IconProps) => (
    <Icon {...props}>
        <path d="M20 8.5V18a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18V6.8" />
        <path d="M4 6.8A1.8 1.8 0 0 1 5.8 5h10.4v3.5" />
        <path d="M16.2 8.5H20v4h-3.8a2 2 0 0 1 0-4Z" />
    </Icon>
)

/* ── Appearance ────────────────────────────────────────────────────── */

export const Sun = (props: IconProps) => (
    <Icon {...props}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4" />
    </Icon>
)

export const Moon = (props: IconProps) => (
    <Icon {...props}>
        <path d="M20 14.2A8.4 8.4 0 0 1 9.8 4a8.5 8.5 0 1 0 10.2 10.2Z" />
    </Icon>
)

/**
 * Follow the system. A half-filled disc: the standard way to say "whichever
 * the surrounding environment is", and it does not pretend to be a device.
 */
export const Contrast = (props: IconProps) => (
    <Icon {...props}>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 3.5v17a8.5 8.5 0 0 0 0-17Z" fill="currentColor" stroke="none" />
    </Icon>
)

/* ── Identity ──────────────────────────────────────────────────────── */

export const User = (props: IconProps) => (
    <Icon {...props}>
        <circle cx="12" cy="8.5" r="3.75" />
        <path d="M5 20a7 7 0 0 1 14 0" />
    </Icon>
)

/** Legal and policy documents. A stamped page, not a shield. */
export const Policy = (props: IconProps) => (
    <Icon {...props}>
        <path d="M18 9.5V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h6.5Z" />
        <path d="M13.5 3v5.5H18" />
        <circle cx="12" cy="15" r="2.5" />
    </Icon>
)
