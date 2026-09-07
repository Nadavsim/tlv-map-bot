import { useState, type FormEvent } from 'react'

interface ChatInputProps {
  disabled: boolean
  onSend: (message: string) => void
}

export function ChatInput({ disabled, onSend }: ChatInputProps) {
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
        placeholder="What are you craving? e.g. 'ramen' or 'coffee'"
        autoComplete="off"
        disabled={disabled}
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button type="submit" disabled={disabled}>
        Send
      </button>
    </form>
  )
}
