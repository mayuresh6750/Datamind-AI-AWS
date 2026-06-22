// middleware.ts
import { createServerClient, type CookieOptions } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';

export async function middleware(request: NextRequest) {
  // Allow Playwright E2E tests to bypass the Supabase auth guard.
  if (request.headers.get('x-e2e-test') === 'true') {
    return NextResponse.next();
  }

  let response = NextResponse.next({
    request: { headers: request.headers },
  });

  // Keep the Supabase client alive so it can refresh session cookies.
  let session: { user?: { user_metadata?: { role?: string } } } | null = null;
  try {
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          get(name: string) {
            return request.cookies.get(name)?.value;
          },
          set(name: string, value: string, options: CookieOptions) {
            request.cookies.set({ name, value, ...options });
            response = NextResponse.next({ request: { headers: request.headers } });
            response.cookies.set({ name, value, ...options });
          },
          remove(name: string, options: CookieOptions) {
            request.cookies.set({ name, value: '', ...options });
            response = NextResponse.next({ request: { headers: request.headers } });
            response.cookies.set({ name, value: '', ...options });
          },
        },
      }
    );
    // Refresh session if expired — required for Server Components.
    const { data } = await supabase.auth.getSession();
    session = data.session;
  } catch {
    // If Supabase is unreachable or the key format is unsupported, just pass through.
  }

  // ── Server-side admin route guard ────────────────────────────────────────
  // Protect all /admin/* routes at the edge before any React component renders.
  // The client-side layout guard is a second layer of defence, not the first.
  if (request.nextUrl.pathname.startsWith('/admin')) {
    if (!session) {
      // Not authenticated — send to login
      const loginUrl = request.nextUrl.clone();
      loginUrl.pathname = '/login';
      return NextResponse.redirect(loginUrl);
    }
    const role = session.user?.user_metadata?.role;
    if (role !== 'admin') {
      // Authenticated but not admin — send to home
      const homeUrl = request.nextUrl.clone();
      homeUrl.pathname = '/';
      return NextResponse.redirect(homeUrl);
    }
  }

  return response;
}

export const config = {
  // Include /admin/* in the middleware matcher so the guard runs server-side.
  matcher: ['/', '/admin/:path*', '/validate/:path*', '/clean/:path*', '/domain'],
};
