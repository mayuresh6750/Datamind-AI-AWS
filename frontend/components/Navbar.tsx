'use client';

import { supabase } from '@/lib/supabase';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore'

export default function Navbar() {
  const router = useRouter();
  const activeDomain = useAuthStore((s) => s.activeDomain)

  const handleLogout = async () => {
    const { error } = await supabase.auth.signOut();
    if (!error) {
      router.push('/login');
    } else {
      console.error('Logout failed:', error.message);
    }
  };

  return (
    <nav className="flex items-center justify-between px-6 py-4 bg-gray-800 text-white">
      <div className="font-bold text-xl">DataMind AI</div>
      <div className='text-sm text-slate-200 mr-4'>Domain: {activeDomain ?? '—'}</div>
      <button
        onClick={handleLogout}
        className="px-4 py-2 text-sm font-medium bg-red-600 rounded hover:bg-red-700 transition"
      >
        Logout
      </button>
      <button onClick={() => router.push('/app/domain')} className="ml-2 px-3 py-1 text-sm rounded border border-white/20">Change domain</button>
    </nav>
  );
}
