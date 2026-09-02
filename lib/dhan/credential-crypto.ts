import 'server-only'
import crypto from 'crypto'

export type DhanCredentialKind = 'api-key' | 'api-secret' | 'access-token'

const PREFIX = 'enc:v2:'

function key() {
  const secret = (
    process.env.DHAN_USER_CREDENTIALS_ENCRYPTION_SECRET
    || process.env.DHAN_TOKEN_ENCRYPTION_KEY
  )?.trim()
  if (!secret) throw new Error('DHAN_USER_CREDENTIALS_ENCRYPTION_SECRET is not configured')
  return crypto.createHash('sha256').update(secret).digest()
}

const aad = (userId: string, kind: DhanCredentialKind) => Buffer.from(`dhan:${userId}:${kind}`)

export function encryptDhanCredential(value: string, userId: string, kind: DhanCredentialKind) {
  const iv = crypto.randomBytes(12)
  const cipher = crypto.createCipheriv('aes-256-gcm', key(), iv)
  cipher.setAAD(aad(userId, kind))
  const ciphertext = Buffer.concat([cipher.update(value, 'utf8'), cipher.final()])
  return `${PREFIX}${iv.toString('base64url')}.${cipher.getAuthTag().toString('base64url')}.${ciphertext.toString('base64url')}`
}

export function decryptDhanCredential(value: string, userId: string, kind: DhanCredentialKind) {
  if (!value.startsWith(PREFIX)) throw new Error('Dhan credential is not encrypted')
  const [iv, tag, ciphertext] = value.slice(PREFIX.length).split('.')
  if (!iv || !tag || !ciphertext) throw new Error('Invalid Dhan credential ciphertext')
  const decipher = crypto.createDecipheriv('aes-256-gcm', key(), Buffer.from(iv, 'base64url'))
  decipher.setAAD(aad(userId, kind))
  decipher.setAuthTag(Buffer.from(tag, 'base64url'))
  return Buffer.concat([
    decipher.update(Buffer.from(ciphertext, 'base64url')),
    decipher.final(),
  ]).toString('utf8')
}
