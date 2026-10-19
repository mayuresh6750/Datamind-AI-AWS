'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { BarChart2, LogOut, Settings } from 'lucide-react';

const NAV_LINKS = [
  { href: '/', label: 'Upload' },
  { href: '/domain', label: 'Domain' },
];

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const activeDomain = useAuthStore((s) => s.activeDomain);
  const clearAuth = useAuthStore((s) => s.clearAuth);

  const handleLogout = () => {
    if (typeof document !== 'undefined') {
      document.cookie = 'datamind_token=; path=/; max-age=0; SameSite=Lax';
      document.cookie = 'datamind_role=; path=/; max-age=0; SameSite=Lax';
    }
    clearAuth();
    router.push('/login');
  };

  return (
    <header className="sticky top-0 z-50 flex h-14 items-center justify-between border-b border-slate-800 bg-slate-900 px-6 shadow-sm">
      {/* ── Brand ── */}
      <div className="flex items-center gap-6">
        <Link href="/" className="flex items-center gap-2 text-white">
          <BarChart2 className="h-5 w-5 text-blue-400" />
          <span className="text-sm font-bold tracking-tight">DataMind AI</span>
        </Link>

        {/* ── Primary nav ── */}
        <nav className="hidden sm:flex items-center gap-1">
          {NAV_LINKS.map(({ href, label }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={[
                  'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  active
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white',
                ].join(' ')}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* ── Right side ── */}
      <div className="flex items-center gap-3">
        {activeDomain && (
          <span className="hidden sm:inline-flex items-center rounded-full border border-blue-500/30 bg-blue-500/10 px-2.5 py-0.5 text-xs font-medium text-blue-300 capitalize">
            {activeDomain}
          </span>
        )}

        <button
          onClick={() => router.push('/domain')}
          className="hidden sm:inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
        >
          <Settings className="h-3.5 w-3.5" />
          Change domain
        </button>

        <button
          onClick={handleLogout}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-red-500/50 hover:bg-red-500/10 hover:text-red-400 transition-colors"
        >
          <LogOut className="h-3.5 w-3.5" />
          Logout
        </button>
      </div>
    </header>
  );
}
