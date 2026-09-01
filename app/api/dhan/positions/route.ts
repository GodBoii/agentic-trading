import { authenticatedDhanGet } from '../_user'

export const dynamic = 'force-dynamic'

export async function GET() {
  return authenticatedDhanGet('/positions', { emptyMessage: 'No positions available' })
}
