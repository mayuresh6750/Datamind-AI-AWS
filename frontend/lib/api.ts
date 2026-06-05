import axios from 'axios'
import { useAuthStore } from '@/store/authStore'

export const api = axios.create({
  baseURL: (process.env.NEXT_PUBLIC_API_URL ?? '') + '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token && config.headers) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true
      try {
        const refresh = useAuthStore.getState().refreshToken
        const { data } = await axios.post(
          (process.env.NEXT_PUBLIC_API_URL ?? '') + '/api/v1/auth/refresh',
          { refresh_token: refresh }
        )
        useAuthStore.getState().setAuth(data)
        original.headers.Authorization = `Bearer ${data.token}`
        return api(original)
      } catch (e) {
        useAuthStore.getState().clearAuth()
        if (typeof window !== 'undefined') window.location.href = '/(auth)/login'
      }
    }
    return Promise.reject(err)
  }
)

export default api
