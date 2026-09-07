interface ChatBubbleProps {
  role: 'bot' | 'user'
  text: string
}

export function ChatBubble({ role, text }: ChatBubbleProps) {
  return <div className={`bubble ${role}`}>{text}</div>
}
