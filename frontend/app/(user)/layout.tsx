"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuthStore } from "@/store/authStore";
import { api } from "@/lib/api";
import Navbar from '@/components/Navbar';

const navItems = [
  { href: "/app", label: "Upload" },
  { href: "/app/datasets", label: "Datasets" },
  { href: "/app/dashboard", label: "Dashboard" },
  { href: "/app/audit", label: "Audit Log" },
];

export default function UserLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const clearAuth = useAuthStore.getState().clearAuth;

  useEffect(() => {
    if (typeof window !== "undefined" && !token) {
      router.push('/login');
    }
  }, [token, router]);

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
      <header className="border-b px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link href="/app" className="font-bold text-lg">
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
