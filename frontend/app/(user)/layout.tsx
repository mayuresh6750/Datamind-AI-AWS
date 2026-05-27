"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/app", label: "Upload" },
  { href: "/app/datasets", label: "Datasets" },
  { href: "/app/dashboard", label: "Dashboard" },
  { href: "/app/audit", label: "Audit Log" },
];

export default function UserLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-3 flex items-center justify-between">
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
      </header>
      <main className="flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
