import axios from 'axios'
import { toastError } from '@/components/AppToast'

export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 120_000,
})

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const body = error?.response?.data?.error
    const message = body ? `[${body.code}] ${body.message}` : error.message
    const trace = error?.response?.headers?.['x-trace-id'] ?? body?.trace_id
    // M1 D13：没有 UI 组件库，用自建 toast；绝不用 ElMessage（会静默失效）
    toastError(trace ? `${message}（trace: ${trace}）` : message)
    return Promise.reject(error)
  },
)

export type Api = typeof http
