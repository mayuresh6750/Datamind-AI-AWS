"use client"
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/authStore'

const DOMAINS = [
  { id: 'finance', label: 'Finance' },
  { id: 'healthcare', label: 'Healthcare' },
  { id: 'retail', label: 'Retail' },
  { id: 'marketing', label: 'Marketing' },
  { id: 'operations', label: 'Operations' },
  { id: 'other', label: 'Other' },
]

export default function DomainModal({ onClose }: { onClose?: () => void }) {
  const router = useRouter()
  const [selected, setSelected] = useState<string>('finance')
  const [descriptor, setDescriptor] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    await api.patch('/datasets/me/domain', {
      domain: selected,
      other_descriptor: selected === 'other' ? descriptor : undefined,
    })
    const st = useAuthStore.getState()
    st.setAuth({
      token: st.token,
      refreshToken: st.refreshToken,
      userId: st.userId,
      role: st.role,
      email: st.email,
      activeDomain: selected,
    })
    setSaving(false)
    if (onClose) onClose()
    else window.location.href = '/'
  }

  return (
    <div className='fixed inset-0 z-50 flex items-center justify-center'>
      <div className='absolute inset-0 bg-black/40' />
      <div className='relative bg-white rounded-lg p-6 w-full max-w-md z-10'>
        <h2 className='text-lg font-semibold mb-2'>Choose your business domain</h2>
        <p className='text-sm text-slate-500 mb-4'>This helps DataMind tailor suggestions to your industry.</p>
        <div className='grid grid-cols-3 gap-2 mb-4'>
          {DOMAINS.map((d) => (
            <button key={d.id} onClick={() => setSelected(d.id)} className={`p-2 rounded border ${selected === d.id ? 'border-primary bg-primary/10' : 'border-slate-200'}`}>
              {d.label}
            </button>
          ))}
        </div>
        {selected === 'other' && (
          <input className='w-full border rounded px-3 py-2 text-sm mb-4' placeholder='Describe your domain (e.g. Legal ops, Education)' value={descriptor} onChange={(e) => setDescriptor(e.target.value)} />
        )}
        <div className='flex justify-end gap-2'>
          <button onClick={() => { if (onClose) onClose(); else router.back() }} className='px-3 py-1 border rounded'>Cancel</button>
          <button onClick={handleSave} disabled={saving} className='px-3 py-1 bg-primary text-white rounded'>{saving ? 'Saving…' : 'Save'}</button>
        </div>
      </div>
    </div>
  )
}
