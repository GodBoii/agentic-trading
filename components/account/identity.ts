/**
 * Identity display rules.
 *
 * A plain module with no React: these are decisions about a string, so keeping
 * them out of the menu component means they can be reasoned about and changed
 * without touching rendering or focus management.
 *
 * Written with explicit scanning rather than regular expressions. The natural
 * version of this uses Unicode property escapes (`\p{L}` with the `u` flag),
 * which this project's `tsconfig` target does not allow, and the ASCII fallback
 * (`[a-z]`) would silently drop the first letter of any non-Latin name. Scanning
 * by code point handles both.
 */

/** True for a character that can start an initial. */
function isLetterish(character: string): boolean {
    const lower = character.toLowerCase()
    const upper = character.toUpperCase()
    // Case-mapping only differs for letters, which is the cheapest reliable
    // letter test available without the `u` flag. Scripts without case (Devanagari,
    // CJK) fail it, so they are caught by the code-point check that follows.
    if (lower !== upper) return true
    const code = character.codePointAt(0) ?? 0
    // Above the Latin-1 supplement and not punctuation, a digit or whitespace.
    return code > 0x00ff
}

/**
 * Up to two initials for the identity tile.
 *
 * Derived from the local part of the address only. `first.last@…` gives FL,
 * `priya@…` gives PR, and anything yielding no letters at all falls back to a
 * neutral glyph rather than rendering an empty tile.
 *
 * Digits never start an initial, so `7ravi@…` reads as RA rather than 7R.
 */
export function initialsFor(email: string | null | undefined): string {
    const local = (email || '').split('@')[0]
    const separators = new Set(['.', '_', '-', '+', ' '])

    const wordInitials: string[] = []
    let atWordStart = true
    for (const character of local) {
        if (separators.has(character)) {
            atWordStart = true
            continue
        }
        if (atWordStart && isLetterish(character)) {
            wordInitials.push(character)
            atWordStart = false
        }
    }

    if (wordInitials.length >= 2) return (wordInitials[0] + wordInitials[1]).toUpperCase()

    // One word: take its first letter plus the next character, so a single-word
    // address still fills the tile.
    const letters = Array.from(local).filter((character) => isLetterish(character))
    if (letters.length >= 2) return (letters[0] + letters[1]).toUpperCase()
    if (letters.length === 1) return letters[0].toUpperCase()
    return '··'
}

/**
 * Splits an address so the menu can show all of it without letting a long domain
 * push the local part out of view.
 *
 * Returning the two halves rather than a pre-truncated string keeps the decision
 * about which half to sacrifice in CSS, where it can respond to the width that is
 * actually available.
 */
export function splitAddress(email: string | null | undefined): { local: string; domain: string } {
    const value = email || ''
    const at = value.lastIndexOf('@')
    if (at <= 0) return { local: value, domain: '' }
    return { local: value.slice(0, at), domain: value.slice(at) }
}
