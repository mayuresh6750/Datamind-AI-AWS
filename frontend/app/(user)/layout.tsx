"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuthStore } from "@/store/authStore";
import Navbar from '@/components/Navbar';
import DomainModal from '@/components/DomainModal';

export default function UserLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const activeDomain = useAuthStore((s) => s.activeDomain);

  const [hydrated, setHydrated] = useState(false);
  useEffect(() => { setHydrated(true); }, []);

  useEffect(() => {
    if (!hydrated) return;
    if (!token) router.push('/login');
  }, [token, hydrated, router]);

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      {hydrated && !activeDomain && pathname !== '/domain' && <DomainModal />}
      <main className="flex-1 px-4 py-6 sm:px-8 sm:py-8 max-w-5xl mx-auto w-full">
        {children}
      </main>
    </div>
  );
}
