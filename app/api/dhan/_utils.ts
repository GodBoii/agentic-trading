import crypto from 'crypto'

const ENCRYPTED_TOKEN_PREFIX = 'enc:v1:'

function encryptionSecret() {
    return process.env.TRADING_KEYS_ENCRYPTION_SECRET || process.env.DHAN_TOKEN_ENCRYPTION_SECRET || ''
}

function toBase64Url(value: Buffer) {
    return value
        .toString('base64')
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/g, '')
}

function fromBase64Url(value: string) {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(normalized.length + ((4 - normalized.length % 4) % 4), '=')
    return Buffer.from(padded, 'base64')
}

function tokenEncryptionKey() {
    const secret = encryptionSecret()
    if (!secret) {
        return null
    }
    return crypto.createHash('sha256').update(secret).digest()
}

export function encryptDhanAccessToken(token: string) {
    const key = tokenEncryptionKey()
    if (!key) {
        return token
    }

    const iv = crypto.randomBytes(12)
    const cipher = crypto.createCipheriv('aes-256-gcm', key, iv)
    const ciphertext = Buffer.concat([cipher.update(token, 'utf8'), cipher.final()])
    const authTag = cipher.getAuthTag()
    return `${ENCRYPTED_TOKEN_PREFIX}${toBase64Url(iv)}.${toBase64Url(authTag)}.${toBase64Url(ciphertext)}`
}

export function decryptDhanAccessToken(storedToken: string) {
    if (!storedToken.startsWith(ENCRYPTED_TOKEN_PREFIX)) {
        return storedToken
    }

    const key = tokenEncryptionKey()
    if (!key) {
        throw new Error('Encrypted Dhan token found but TRADING_KEYS_ENCRYPTION_SECRET is not configured')
    }

    const [ivText, authTagText, ciphertextText] = storedToken
        .slice(ENCRYPTED_TOKEN_PREFIX.length)
        .split('.')
    if (!ivText || !authTagText || !ciphertextText) {
        throw new Error('Invalid encrypted Dhan token format')
    }

    const decipher = crypto.createDecipheriv('aes-256-gcm', key, fromBase64Url(ivText))
    decipher.setAuthTag(fromBase64Url(authTagText))
    return Buffer.concat([
        decipher.update(fromBase64Url(ciphertextText)),
        decipher.final(),
    ]).toString('utf8')
}

export function parseDhanExpiryIso(expiryTime: unknown) {
    if (typeof expiryTime !== 'string' || expiryTime.trim() === '') {
        return null
    }

    const compact = expiryTime.trim().replace(' ', 'T')
    const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(compact)
    const date = new Date(hasTimezone ? compact : `${compact}+05:30`)
    return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

export function dhanApiHeaders(accessToken: string): HeadersInit {
    return {
        'Content-Type': 'application/json',
        'access-token': accessToken,
    }
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
