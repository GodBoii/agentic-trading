const DEFAULT_TIMEOUT_MS = 5_000

/**
 * Supabase's default fetch can wait longer than Vercel allows middleware to
 * run. Abort upstream calls early so an auth outage never becomes a platform
 * gateway timeout.
 */
export function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)

  const abortFromCaller = () => controller.abort()
  init.signal?.addEventListener('abort', abortFromCaller, { once: true })

  return fetch(input, {
    ...init,
    signal: controller.signal,
  }).finally(() => {
    clearTimeout(timeout)
    init.signal?.removeEventListener('abort', abortFromCaller)
  })
}
