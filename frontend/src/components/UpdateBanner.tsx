import { useState } from 'react'
import { RefreshCw, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface Props {
  serverVersion: string | null
}

export default function UpdateBanner({ serverVersion }: Props) {
  const { t } = useTranslation('auth')
  const [isUpdating, setIsUpdating] = useState(false)

  const handleUpdate = async () => {
    setIsUpdating(true)
    try {
      if ('serviceWorker' in navigator) {
        const reg = await navigator.serviceWorker.getRegistration()
        if (reg?.waiting) {
          reg.waiting.postMessage({ type: 'SKIP_WAITING' })
        }
        if (reg) {
          await reg.update()
          await new Promise<void>(resolve => {
            const onControllerChange = () => {
              navigator.serviceWorker.removeEventListener('controllerchange', onControllerChange)
              resolve()
            }
            navigator.serviceWorker.addEventListener('controllerchange', onControllerChange)
            setTimeout(resolve, 3000)
          })
        }
        const keys = await caches.keys()
        await Promise.all(keys.map(k => caches.delete(k)))
      }
    } catch {
      // ignore
    }
    window.location.replace('/?_v=' + Date.now())
  }

  return (
    <div className="fixed bottom-[calc(env(safe-area-inset-bottom)+4rem)] inset-x-0 z-[90] flex justify-center px-4 pointer-events-none">
      <div className="flex items-center gap-3 rounded-card bg-accent px-4 py-3 shadow-xl pointer-events-auto">
        <span className="text-body font-semibold text-accent-fg">
          v{__APP_VERSION__} → v{serverVersion ?? '?'}
        </span>
        <button
          onClick={handleUpdate}
          disabled={isUpdating}
          className="flex items-center gap-2 rounded-card bg-accent-fg/20 px-3 py-2 text-label font-bold text-accent-fg active:opacity-70 disabled:opacity-60"
        >
          {isUpdating
            ? <Loader2 size={12} className="animate-spin" />
            : <RefreshCw size={12} />
          }
          {isUpdating ? t('updating') : t('updateButton')}
        </button>
      </div>
    </div>
  )
}
