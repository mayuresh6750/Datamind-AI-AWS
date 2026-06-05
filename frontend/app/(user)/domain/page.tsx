"use client"
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { DomainCard } from '@/components/user/DomainCard'
import { Button } from '@/components/ui/Button'

const DOMAINS = [
  { id: 'finance', label: 'Finance', icon: 'TrendingUp', kpis: 'MRR · ARR · Churn · Runway' },
  { id: 'healthcare', label: 'Healthcare', icon: 'HeartPulse', kpis: 'Readmission · LOS · Episodes' },
  { id: 'retail', label: 'Retail / eCommerce', icon: 'ShoppingCart', kpis: 'AOV · SKU margin · Return rate' },
  { id: 'marketing', label: 'Marketing', icon: 'Megaphone', kpis: 'CTR · CAC · LTV · CPA' },
  { id: 'operations', label: 'Operations', icon: 'Settings', kpis: 'Throughput · Cycle time' },
  { id: 'other', label: 'Other', icon: 'LayoutGrid', kpis: 'Generic pack' },
] as const

export default function DomainPage() {
  const router = useRouter()
  const setAuth = useAuthStore.getState().setAuth
  const [selected, setSelected] = useState<string>('finance')
  const [descriptor, setDescriptor] = useState('')
  const [saving, setSaving] = useState(false)
  const handleContinue = async () => {
    setSaving(true)
    await api.patch('/datasets/me/domain', {
      domain: selected,
      descriptor: selected === 'other' ? descriptor : undefined,
    })
    setSaving(false)
    const st = useAuthStore.getState()
    st.setAuth({
      token: st.token,
      refreshToken: st.refreshToken,
      userId: st.userId,
      role: st.role,
      email: st.email,
      activeDomain: selected,
    })
    router.push('/upload')
  }
  return (
    <div className='max-w-2xl'>
      <h1 className='text-xl font-semibold mb-1'>Welcome to DataMind</h1>
      <p className='text-sm text-slate-500 mb-6'>Select your primary business domain so agents can speak your language.</p>
      <div className='grid grid-cols-3 gap-3 mb-6'>
        {DOMAINS.map((d) => (
          <DomainCard key={d.id} domain={d} selected={selected === d.id} onSelect={() => setSelected(d.id)} />
        ))}
      </div>
      {selected === 'other' && (
        <input className='w-full border rounded px-3 py-2 text-sm mb-4' placeholder='Describe your domain (e.g. Legal ops, Education)' value={descriptor} onChange={(e) => setDescriptor(e.target.value)} />
      )}
      <Button onClick={handleContinue} disabled={saving}>{saving ? 'Saving…' : `Continue with ${DOMAINS.find((d) => d.id === selected)?.label}`}</Button>
    </div>
  )
}
