import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import { fetchWithTimeout } from '@/lib/supabase/fetch-with-timeout'

export async function middleware(request: NextRequest) {
    const pathname = request.nextUrl.pathname

    // Public routes must remain available even when the auth service is down.
    // Check this before making any network request to Supabase.
    const publicPaths = ['/', '/login', '/signup', '/signin', '/singin', '/auth', '/api/dhan/callback', '/api/dhan/postback']
    const isPublic = publicPaths.some(p =>
        p === '/' ? pathname === '/' : pathname === p || pathname.startsWith(`${p}/`)
    )

    if (isPublic) {
        return NextResponse.next()
    }

    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
    const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

    if (!supabaseUrl || !supabaseAnonKey) {
        console.error('Supabase auth is not configured')
        return authUnavailableResponse(request)
    }

    let supabaseResponse = NextResponse.next({
        request,
    })

    const supabase = createServerClient(
        supabaseUrl,
        supabaseAnonKey,
        {
            global: {
                fetch: fetchWithTimeout,
            },
            cookies: {
                getAll() {
                    return request.cookies.getAll()
                },
                setAll(cookiesToSet) {
                    cookiesToSet.forEach(({ name, value, options }) => request.cookies.set(name, value))
                    supabaseResponse = NextResponse.next({
                        request,
                    })
                    cookiesToSet.forEach(({ name, value, options }) =>
                        supabaseResponse.cookies.set(name, value, options)
                    )
                },
            },
        }
    )

    let user = null
    try {
        // Validate and refresh the session, but never let an upstream outage
        // consume Vercel's entire middleware execution window.
        const result = await supabase.auth.getUser()
        if (result.error) {
            console.warn('Supabase auth check failed:', result.error.message)
            if (result.error.name === 'AuthRetryableFetchError') {
                return authUnavailableResponse(request)
            }
        }
        user = result.data.user
    } catch (error) {
        console.error('Supabase auth request failed:', error)
        return authUnavailableResponse(request)
    }

    // Protect private routes - redirect to login if not authenticated
    if (!user) {
        const redirectUrl = request.nextUrl.clone()
        redirectUrl.pathname = '/login'
        return NextResponse.redirect(redirectUrl)
    }

    return supabaseResponse
}

function authUnavailableResponse(request: NextRequest) {
    if (request.nextUrl.pathname.startsWith('/api/')) {
        return NextResponse.json(
            { error: 'Authentication service unavailable' },
            { status: 503 },
        )
    }

    const redirectUrl = request.nextUrl.clone()
    redirectUrl.pathname = '/login'
    redirectUrl.searchParams.set('error', 'auth_unavailable')
    return NextResponse.redirect(redirectUrl)
}

export const config = {
    matcher: [
        '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
    ],
}
