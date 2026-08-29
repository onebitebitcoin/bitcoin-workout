import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import { useAuthStore } from '../store/auth'

const client = axios.create({
  baseURL: '/api/v1',
})

client.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// access token 만료(401) 시 refresh token으로 1회 자동 갱신.
// 동시에 여러 요청이 401을 받아도 refresh는 한 번만 수행하고 나머지는 대기시킨다.
let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refreshToken = useAuthStore.getState().refreshToken
  if (!refreshToken) throw new Error('no refresh token')
  // baseURL만 사용하는 raw axios로 호출 — 인터셉터 재귀 방지
  const res = await axios.post<{ data: { access_token: string; refresh_token: string } }>(
    '/api/v1/auth/refresh',
    { refresh_token: refreshToken },
  )
  const { access_token, refresh_token } = res.data.data
  useAuthStore.getState().setTokens(access_token, refresh_token)
  return access_token
}

client.interceptors.response.use(
  (res) => res,
  async (err: AxiosError) => {
    const original = err.config as (AxiosRequestConfig & { _retry?: boolean }) | undefined
    const status = err.response?.status

    // refresh 엔드포인트 자체의 401이거나, 이미 재시도한 요청이면 바로 로그아웃
    const isRefreshCall = original?.url?.includes('/auth/refresh')
    if (status === 401 && original && !original._retry && !isRefreshCall) {
      if (!useAuthStore.getState().refreshToken) {
        useAuthStore.getState().logout()
        return Promise.reject(err)
      }
      original._retry = true
      try {
        if (!refreshPromise) {
          refreshPromise = refreshAccessToken().finally(() => {
            refreshPromise = null
          })
        }
        const newToken = await refreshPromise
        original.headers = { ...original.headers, Authorization: `Bearer ${newToken}` }
        return client(original)
      } catch {
        useAuthStore.getState().logout()
        return Promise.reject(err)
      }
    }

    if (status === 401) {
      useAuthStore.getState().logout()
    }
    return Promise.reject(err)
  },
)

export default client
