'use client';

import { supabase } from '@/lib/supabase';
import { useRouter } from 'next/navigation';

export default function Navbar() {
  const router = useRouter();

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
      <div className="font-bold text-xl">My App</div>
      <button
        onClick={handleLogout}
        className="px-4 py-2 text-sm font-medium bg-red-600 rounded hover:bg-red-700 transition"
      >
        Logout
      </button>
    </nav>
  );
}
