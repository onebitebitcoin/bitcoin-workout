import toast from 'react-hot-toast'
import type { TFunction } from 'i18next'

export function shareProfileLink(userId: number, username: string, t: TFunction) {
  const url = `${window.location.origin}/users/${userId}`
  const text = t('shareProfileText', { username })

  const copyToClipboard = () =>
    window.navigator.clipboard?.writeText(url)
      .then(() => toast.success(t('shareProfileCopied')))
      .catch(() => toast(url))

  if (typeof navigator !== 'undefined' && 'share' in navigator) {
    navigator
      .share({ title: 'Bitcoiners', text, url })
      .catch((err) => {
        if (!(err instanceof DOMException && err.name === 'AbortError')) copyToClipboard()
      })
  } else {
    copyToClipboard()
  }
}
