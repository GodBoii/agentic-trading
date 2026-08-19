/**
 * Motion system — public surface.
 *
 * Each export wraps exactly one recipe from the project's motion catalogue, so
 * a component picks a transition by naming the interaction rather than by
 * hand-rolling durations. The CSS lives in `app/globals.css` under
 * `MOTION RECIPES`; these are the orchestration layers for the recipes that
 * need one.
 *
 * Choosing between them:
 *   - anchored surface growing from a trigger → `Dropdown`
 *   - centred surface demanding a response    → `Modal`
 *   - trigger that becomes the surface        → `Morph`
 *   - transient confirmation                  → `Toast`
 *   - header with a collapsible body          → `Accordion`
 *   - two side-by-side views                  → `PageSwitch`
 *   - placeholder swapping to real content    → `SkeletonReveal`
 *   - a label changing in place               → `TextSwap`
 *   - two icons in one slot                   → `IconSwap`
 *   - a figure that updated                   → `NumberFlow`
 *   - a count that is an event                → `SpinningCounter`
 *   - in-progress prose                       → `Shimmer`
 *   - semantic agent activity                 → `ThinkingOrb`
 *   - completion worth marking                → `SuccessCheck`
 *   - form validation feedback                → `useErrorShake`
 */

export { motionMs, motionNum, motionEase, prefersReducedMotion, forceReflow } from './tokens'

export { Reveal, RevealBlock, useReveal, useRevealList } from './reveal'
export { TextSwap } from './text-swap'
export { IconSwap } from './icon-swap'
export { NumberFlow, SpinningCounter } from './number-flow'

export { Modal, useModal } from './modal'
export { Dropdown, useDropdown, type DropdownOrigin } from './dropdown'
export { Toast, useToast, type ToastMessage, type ToastTone } from './toast'
export { Accordion, AccordionShell, AccordionChevron, DisclosurePanel } from './accordion'
export { PageSwitch } from './page-switch'
export { Morph } from './morph'

export { SkeletonReveal } from './skeleton-reveal'
export { Shimmer } from './shimmer'
export { ThinkingOrb, type OrbState } from './thinking-orb'
export { SuccessCheck, SuccessBadge } from './success-check'
export { useErrorShake, ErrorMessage } from './error-field'
export { NotificationBadge } from './notification-badge'

export { Tooltip } from './tooltip'
export { Toggle } from './toggle'
export { Checkbox } from './checkbox'
export { LearnMoreChevron } from './learn-more'
export { ClearableInput } from './clearable-input'

export { Tilt } from './tilt'
export { useHoverGroup } from './hover-group'
export { BorderBeam, type BeamMode, type BeamTone } from './border-beam'
