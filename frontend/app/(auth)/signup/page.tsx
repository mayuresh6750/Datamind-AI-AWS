"use client"
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import { BarChart2, Loader2 } from 'lucide-react'

export default function SignupPage() {
  const router = useRouter()
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr]           = useState('')
  const [loading, setLoading]   = useState(false)

  const handleSignup = async () => {
    if (!email || !password) { setErr('Please enter your email and password.'); return }
    if (password.length < 8) { setErr('Password must be at least 8 characters.'); return }
    setLoading(true)
    setErr('')
    try {
      const { error } = await supabase.auth.signUp({ email, password })
      if (error) { setErr(error.message); return }
      router.push('/domain')
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Sign up failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
      {/* Brand mark */}
      <div className="mb-8 flex flex-col items-center gap-2">
        <div className="flex items-center justify-center h-11 w-11 rounded-xl bg-blue-600 shadow-lg shadow-blue-600/30">
          <BarChart2 className="h-6 w-6 text-white" />
        </div>
        <span className="text-lg font-bold text-slate-900 tracking-tight">DataMind AI</span>
        <p className="text-sm text-slate-500">Create your free workspace</p>
      </div>

      {/* Card */}
      <div className="auth-card">
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-slate-700" htmlFor="email">
              Work email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSignup()}
              placeholder="you@company.com"
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 transition-colors"
            />
          </div>

          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-slate-700" htmlFor="password">
              Password
              <span className="ml-1 font-normal text-slate-400">(min. 8 characters)</span>
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSignup()}
              placeholder="••••••••"
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 transition-colors"
            />
          </div>

          {err && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
              {err}
            </div>
          )}

          <button
            onClick={handleSignup}
            disabled={loading}
            className="btn-primary w-full justify-center py-2.5"
          >
            {loading ? <><Loader2 className="h-4 w-4 animate-spin" /> Creating account…</> : 'Create account'}
          </button>
        </div>

        <div className="mt-1 text-center text-sm text-slate-500">
          Already have an account?{' '}
          <Link href="/login" className="font-medium text-blue-600 hover:text-blue-700 hover:underline">
            Sign in
          </Link>
        </div>
      </div>

      <p className="mt-6 text-center text-xs text-slate-400 max-w-xs">
        By creating an account you agree to our Terms of Service and Privacy Policy.
      </p>
    </div>
  )
}
