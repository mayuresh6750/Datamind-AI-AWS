// middleware.ts
import { createServerClient, type CookieOptions } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';

// Routes that authenticated users should NOT be able to visit (redirect to home).
const AUTH_ROUTES = ['/login', '/signup'];

// Routes that require authentication (redirect to login if no session).
const PROTECTED_PREFIXES = ['/', '/validate', '/clean', '/intent', '/dashboard', '/domain'];

function isProtected(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) =>
    p === '/' ? pathname === '/' : pathname.startsWith(p)
  );
}

export async function middleware(request: NextRequest) {
  // Allow Playwright E2E tests to bypass the Supabase auth guard.
  if (request.headers.get('x-e2e-test') === 'true') {
    return NextResponse.next();
  }

  let response = NextResponse.next({
    request: { headers: request.headers },
  });

  // Build Supabase server client so session cookies are refreshed on every request.
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
    const { data } = await supabase.auth.getSession();
    session = data.session;
  } catch {
    // Supabase unreachable — fall through and let client-side auth handle it.
  }

  const { pathname } = request.nextUrl;

  // ── Admin route guard ─────────────────────────────────────────────────────
  if (pathname.startsWith('/admin')) {
    if (!session) {
      const url = request.nextUrl.clone();
      url.pathname = '/login';
      return NextResponse.redirect(url);
    }
    const role = session.user?.user_metadata?.role;
    if (role !== 'admin') {
      const url = request.nextUrl.clone();
      url.pathname = '/';
      return NextResponse.redirect(url);
    }
    return response;
  }

  // ── User route guard — redirect unauthenticated users to /login ───────────
  if (isProtected(pathname) && !session) {
    const url = request.nextUrl.clone();
    url.pathname = '/login';
    return NextResponse.redirect(url);
  }

  // ── Auth page guard — redirect already-logged-in users away from /login ───
  if (AUTH_ROUTES.includes(pathname) && session) {
    const url = request.nextUrl.clone();
    url.pathname = '/';
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  matcher: ['/', '/login', '/signup', '/admin/:path*', '/validate/:path*', '/clean/:path*', '/intent/:path*', '/dashboard/:path*', '/domain'],
};
