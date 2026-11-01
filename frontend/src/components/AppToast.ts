/** 零依赖 toast：M1 起不引入 UI 组件库（D13），错误提示必须自己实现。 */
let host: HTMLDivElement | null = null

function ensureHost(): HTMLDivElement {
  if (!host) {
    host = document.createElement('div')
    host.className = 'toast-host'
    document.body.appendChild(host)
  }
  return host
}

export function toast(message: string, kind: 'info' | 'error' | 'success' = 'info', ms = 4200) {
  const el = document.createElement('div')
  el.className = `toast toast-${kind}`
  el.textContent = message
  ensureHost().appendChild(el)
  setTimeout(() => {
    el.classList.add('toast-out')
    setTimeout(() => el.remove(), 220)
  }, ms)
}

export const toastError = (message: string) => toast(message, 'error', 6000)
export const toastInfo = (message: string) => toast(message, 'info')
export const toastSuccess = (message: string) => toast(message, 'success')
