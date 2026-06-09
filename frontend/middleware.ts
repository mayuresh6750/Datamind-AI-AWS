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

  // Keep the Supabase client alive so it can refresh session cookies,
  // but do NOT redirect — the client-side UserLayout handles auth protection.
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
    await supabase.auth.getSession();
  } catch {
    // If Supabase is unreachable or the key format is unsupported, just pass through.
  }

  return response;
}

export const config = {
  matcher: ['/', '/validate/:path*', '/clean/:path*', '/domain'],
};
