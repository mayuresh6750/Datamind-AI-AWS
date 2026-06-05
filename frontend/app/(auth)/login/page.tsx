"use client"
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
})
type FormData = z.infer<typeof schema>

export default function LoginPage() {
  const router = useRouter()
  const setAuth = useAuthStore.getState().setAuth
  const [err, setErr] = useState('')
  const { register, handleSubmit, formState: { isSubmitting } } = useForm<FormData>({ resolver: zodResolver(schema) })
  const onSubmit = async (data: FormData) => {
    try {
      const res = await api.post('/auth/login', data)
      setAuth(res.data)
      router.push(res.data.role === 'admin' ? '/admin/health' : '/domain')
    } catch (e: any) {
      const status = e.response?.status
      if (status === 401) setErr('Invalid credentials')
      else if (status === 400 && e.response?.data?.detail) setErr(e.response.data.detail)
      else setErr(e.response?.data?.detail || 'Login failed')
    }
  }
  return (
    <div className='min-h-screen flex items-center justify-center bg-slate-50'>
      <div className='w-full max-w-sm p-8 bg-white rounded-xl border border-slate-200'>
        <h1 className='text-xl font-semibold mb-1'>Sign in to DataMind</h1>
        <p className='text-sm text-slate-500 mb-6'>Enter your email and password to continue.</p>
        <form onSubmit={handleSubmit(onSubmit)} className='space-y-4'>
          <div>
            <Label htmlFor='email'>Email</Label>
            <Input id='email' type='email' {...register('email')} />
          </div>
          <div>
            <Label htmlFor='password'>Password</Label>
            <Input id='password' type='password' {...register('password')} />
          </div>
          {err && <p className='text-sm text-red-600'>{err}</p>}
          <Button type='submit' className='w-full' disabled={isSubmitting}>{isSubmitting ? 'Signing in…' : 'Sign in'}</Button>
        </form>
      </div>
    </div>
  )
}
