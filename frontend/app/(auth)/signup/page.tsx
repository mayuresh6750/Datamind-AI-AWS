"use client";

import { supabase } from '@/lib/supabase';
import { useRouter } from 'next/navigation';
import AuthForm from '@/components/AuthForm';

export default function SignupPage() {
  const router = useRouter();

  const handleSignup = async (email: string, password: string) => {
    const { error } = await supabase.auth.signUp({ email, password });
    if (error) {
      return { error: error.message };
    }
    // If email confirmations are required, user must confirm via email.
    router.push('/app/dashboard');
    return { error: null };
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <AuthForm type="signup" onSubmit={handleSignup} />
    </div>
  );
}
