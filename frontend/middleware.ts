import { NextResponse, type NextRequest } from 'next/server';

// Routes that authenticated users should NOT be able to visit (redirect to home).
const AUTH_ROUTES = ['/login', '/signup'];

// Routes that require authentication (redirect to login if no session).
const PROTECTED_PREFIXES = ['/validate', '/clean', '/intent', '/dashboard', '/domain'];

function isProtected(pathname: string): boolean {
  if (pathname === '/') return true;
  return PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
}

export function middleware(request: NextRequest) {
  // Allow Playwright E2E tests to bypass the auth guard.
  if (request.headers.get('x-e2e-test') === 'true') {
    return NextResponse.next();
  }

  const token = request.cookies.get('datamind_token')?.value;
  const role = request.cookies.get('datamind_role')?.value || 'user';
  const { pathname } = request.nextUrl;

  // 1. Admin route guard
  if (pathname.startsWith('/admin')) {
    if (!token) {
      const url = request.nextUrl.clone();
      url.pathname = '/login';
      return NextResponse.redirect(url);
    }
    if (role !== 'admin') {
      const url = request.nextUrl.clone();
      url.pathname = '/';
      return NextResponse.redirect(url);
    }
    return NextResponse.next();
  }

  // 2. Protected user route guard
  if (isProtected(pathname) && !token) {
    const url = request.nextUrl.clone();
    url.pathname = '/login';
    return NextResponse.redirect(url);
  }

  // 3. Auth page guard (redirect logged-in users away from /login & /signup)
  if (AUTH_ROUTES.includes(pathname) && token) {
    const url = request.nextUrl.clone();
    url.pathname = role === 'admin' ? '/admin' : '/';
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    '/',
    '/login',
    '/signup',
    '/admin/:path*',
    '/validate/:path*',
    '/clean/:path*',
    '/intent/:path*',
    '/dashboard/:path*',
    '/domain',
  ],
};
