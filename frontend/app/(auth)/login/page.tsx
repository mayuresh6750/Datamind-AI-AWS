"use client"
import { useState } from 'react'
import { useAuthStore } from '@/store/authStore'
import { supabase } from '@/lib/supabase'

export default function LoginPage() {
  const setAuth = useAuthStore.getState().setAuth
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr]           = useState('')
  const [loading, setLoading]   = useState(false)

  const handleSignIn = async () => {
    if (!email || !password) { setErr('Please enter email and password'); return }
    setLoading(true)
    setErr('')
    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const body = await res.json()
      if (!res.ok) {
        setErr(body.detail ?? 'Invalid credentials')
        setLoading(false)
        return
      }
      // Sync session into Supabase client so middleware cookies are written
      await supabase.auth.setSession({
        access_token:  body.access_token,
        refresh_token: body.refresh_token,
      }).catch(() => {})

      setAuth({
        token:        body.access_token  ?? null,
        refreshToken: body.refresh_token ?? null,
        userId:       body.user_id       ?? null,
        role:         body.role          ?? 'user',
        email,
        activeDomain: null,
      })
      window.location.href = body.role === 'admin' ? '/admin/health' : '/domain'
    } catch (e: any) {
      setErr(e.message || 'Login failed')
      setLoading(false)
    }
  }

  return (
    <div className='min-h-screen flex items-center justify-center bg-slate-50'>
      <div className='w-full max-w-sm p-8 bg-white rounded-xl border border-slate-200 space-y-4'>
        <h1 className='text-xl font-semibold'>Sign in to DataMind</h1>
        <p className='text-sm text-slate-500'>Enter your email and password to continue.</p>
        <div className='space-y-1'>
          <label className='text-sm font-medium'>Email</label>
          <input type='email' value={email} onChange={e => setEmail(e.target.value)}
            className='w-full border rounded-md px-3 py-2 text-sm' placeholder='you@example.com' />
        </div>
        <div className='space-y-1'>
          <label className='text-sm font-medium'>Password</label>
          <input type='password' value={password} onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSignIn()}
            className='w-full border rounded-md px-3 py-2 text-sm' placeholder='••••••••' />
        </div>
        {err && <p className='text-sm text-red-600'>{err}</p>}
        <button onClick={handleSignIn} disabled={loading}
          className='w-full rounded-md bg-blue-600 py-2.5 text-sm font-medium text-white disabled:opacity-50'>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </div>
    </div>
  )
}
