"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const adminNav = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/llm", label: "LLM Providers" },
  { href: "/admin/domain-packs", label: "Domain Packs" },
  { href: "/admin/audit", label: "Audit Log" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 border-r px-4 py-6 space-y-1">
        <p className="px-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">Admin</p>
        {adminNav.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`block rounded-md px-2 py-1.5 text-sm ${
              pathname === item.href
                ? "bg-accent font-semibold"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </aside>
      <main className="flex-1 px-8 py-6">{children}</main>
    </div>
  );
}
