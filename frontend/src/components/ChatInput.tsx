import { useState, type FormEvent } from 'react'
import { t } from '../i18n'
import type { Lang } from '../types'

interface ChatInputProps {
  disabled: boolean
  onSend: (message: string) => void
  lang: Lang
}

export function ChatInput({ disabled, onSend, lang }: ChatInputProps) {
  const [value, setValue] = useState('')

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const message = value.trim()
    if (!message) return
    setValue('')
    onSend(message)
  }

  return (
    <form className="chat-form" onSubmit={handleSubmit}>
      <input
        type="text"
        placeholder={t(lang, 'chatPlaceholder')}
        autoComplete="off"
        disabled={disabled}
        value={value}
        maxLength={500}
        onChange={(e) => setValue(e.target.value)}
      />
      <button type="submit" disabled={disabled}>
        {t(lang, 'chatSend')}
      </button>
    </form>
  )
}
