/**
 * Minimal conditional class joiner.
 *
 * Deliberately not `clsx` + `tailwind-merge`: the components in this app take
 * closed variant props rather than accepting arbitrary overriding classes, so
 * conflict resolution is never needed. This keeps the dependency count flat.
 */
export type ClassValue = string | number | false | null | undefined

export function cn(...values: ClassValue[]): string {
    let result = ''
    for (const value of values) {
        if (!value && value !== 0) continue
        result = result ? `${result} ${value}` : String(value)
    }
    return result
}
