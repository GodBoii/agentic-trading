export function parseDhanExpiryIso(expiryTime: unknown) {
    if (typeof expiryTime !== 'string' || expiryTime.trim() === '') {
        return null
    }

    const compact = expiryTime.trim().replace(' ', 'T')
    const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(compact)
    const date = new Date(hasTimezone ? compact : `${compact}+05:30`)
    return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

export async function readDhanError(response: Response, fallbackMessage: string) {
    const errorText = await response.text()
    let errorJson: any = {}
    try {
        errorJson = JSON.parse(errorText)
    } catch (e) {
        // Dhan occasionally returns text bodies for gateway or proxy errors.
    }

    const errorMessage =
        errorJson.errorMessage ||
        errorJson.message ||
        (errorText ? `Dhan API Error: ${errorText.substring(0, 100)}` : fallbackMessage)

    return { errorText, errorJson, errorMessage }
}
