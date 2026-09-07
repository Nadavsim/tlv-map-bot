import { t } from '../i18n'
import type { Lang } from '../types'

export function TypingIndicator({ lang }: { lang: Lang }) {
  return (
    <div className="bubble bot typing-indicator" aria-label={t(lang, 'waitingForReply')}>
      <span />
      <span />
      <span />
    </div>
  )
}
