"use client"
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/store/authStore'
import { BarChart2, Loader2 } from 'lucide-react'

function extractLoginError(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  return 'Login failed. Please try again.'
}

export default function LoginPage() {
  const setAuth = useAuthStore.getState().setAuth
  const router = useRouter()
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr]           = useState('')
  const [loading, setLoading]   = useState(false)

  const handleSignIn = async () => {
    if (!email || !password) { setErr('Please enter your email and password.'); return }
    setLoading(true)
    setErr('')
    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })

      let body: any = {}
      try { body = await res.json() } catch {
        setErr(res.ok ? 'Invalid response from server.' : `Server error (${res.status}). Is the backend running?`)
        return
      }

      if (!res.ok) { setErr(body.detail ?? 'Invalid credentials'); return }

      if (typeof document !== 'undefined') {
        document.cookie = `datamind_token=${body.access_token}; path=/; max-age=604800; SameSite=Lax`
        document.cookie = `datamind_role=${body.role ?? 'user'}; path=/; max-age=604800; SameSite=Lax`
      }

      setAuth({
        token:        body.access_token  ?? null,
        refreshToken: body.refresh_token ?? null,
        userId:       body.user_id       ?? null,
        role:         body.role          ?? 'user',
        email,
        activeDomain: body.active_domain ?? null,
      })
      // If backend returned an existing domain, go straight to upload; otherwise prompt for domain
      const hasDomain = !!body.active_domain
      router.push(body.role === 'admin' ? '/admin' : hasDomain ? '/' : '/domain')
    } catch (e: unknown) {
      setErr(extractLoginError(e))
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
        <p className="text-sm text-slate-500">Sign in to your workspace</p>
      </div>

      {/* Card */}
      <div className="auth-card">
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-slate-700" htmlFor="email">
              Email address
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSignIn()}
              placeholder="you@company.com"
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 transition-colors"
            />
          </div>

          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-slate-700" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSignIn()}
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
            onClick={handleSignIn}
            disabled={loading}
            className="btn-primary w-full justify-center py-2.5"
          >
            {loading ? <><Loader2 className="h-4 w-4 animate-spin" /> Signing in…</> : 'Sign in'}
          </button>
        </div>

        <div className="mt-1 text-center text-sm text-slate-500">
          Don&apos;t have an account?{' '}
          <Link href="/signup" className="font-medium text-blue-600 hover:text-blue-700 hover:underline">
            Create one
          </Link>
        </div>
      </div>
    </div>
  )
}
