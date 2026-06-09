"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuthStore } from "@/store/authStore";
import { api } from "@/lib/api";
import Navbar from '@/components/Navbar';
import DomainModal from '@/components/DomainModal';

const navItems = [
  { href: "/", label: "Upload" },
  { href: "/domain", label: "Domain" },
];

export default function UserLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const activeDomain = useAuthStore((s) => s.activeDomain);
  const clearAuth = useAuthStore.getState().clearAuth;

  // Wait for Zustand to rehydrate from localStorage before evaluating auth.
  // Without this gate the layout redirects to /login on first render because
  // the store starts null and only receives the persisted value after mount.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    if (!token) {
      router.push('/login');
    }
  }, [token, hydrated, router]);

  async function handleLogout() {
    try {
      await api.post('/auth/logout');
    } catch (e) {
      // ignore errors, still clear local session
    }
    clearAuth();
    router.push('/login');
  }

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      {/* Only show the domain modal after Zustand has hydrated from localStorage.
          Without this guard the modal flashes on every page load because the store
          starts with activeDomain = null before the persisted value is read. */}
      {hydrated && !activeDomain && pathname !== '/domain' && <DomainModal />}
      <header className="border-b px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link href="/" className="font-bold text-lg">
            DataMind AI
          </Link>
          <nav className="flex gap-4 text-sm">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={pathname === item.href ? "font-semibold text-primary" : "text-muted-foreground hover:text-foreground"}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <main className="flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
