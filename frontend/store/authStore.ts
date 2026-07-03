import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Role = 'user' | 'admin'

interface AuthState {
  token: string | null
  refreshToken: string | null
  userId: string | null
  role: Role | null
  email: string | null
  activeDomain: string | null
  setAuth: (data: Omit<AuthState, 'setAuth' | 'clearAuth'>) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      userId: null,
      role: null,
      email: null,
      activeDomain: null,
      // Preserve activeDomain if caller doesn't supply one — prevents a token
      // refresh from wiping the user's selected domain mid-pipeline.
      setAuth: (d) => set((state) => ({
        ...d,
        activeDomain: 'activeDomain' in d ? d.activeDomain : state.activeDomain,
      })),
      clearAuth: () =>
        set({
          token: null,
          refreshToken: null,
          userId: null,
          role: null,
          email: null,
          activeDomain: null,
        }),
    }),
    { name: 'datamind-auth' }
  )
)
