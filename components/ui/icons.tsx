import type { SVGProps } from 'react'

/**
 * A small, deliberate icon set.
 *
 * The UI previously used text glyphs (`→`, `←`, `↻`, `+`, `×`) which render at
 * inconsistent weights and baselines across fonts. These are 16px stroke icons
 * on a 24px grid, inheriting `currentColor` and stroke width, so they align
 * optically with 11–13px type. Hand-rolled rather than pulling in an icon
 * package for ten glyphs.
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

export const Refresh = (props: IconProps) => (
    <Icon {...props}>
        <path d="M20 11a8 8 0 1 0-2.3 5.7" />
        <path d="M20 5v6h-6" />
    </Icon>
)

export const Alert = (props: IconProps) => (
    <Icon {...props}>
        <path d="M12 9v4M12 17h.01" />
        <path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
    </Icon>
)

export const External = (props: IconProps) => (
    <Icon {...props}>
        <path d="M14 4h6v6M20 4l-8.5 8.5" />
        <path d="M19 14v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </Icon>
)

export const Document = (props: IconProps) => (
    <Icon {...props}>
        <path d="M14 3v5h5" />
        <path d="M19 8v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h8Z" />
        <path d="M9 13h6M9 17h4" />
    </Icon>
)


