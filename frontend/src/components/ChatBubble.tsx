interface ChatBubbleProps {
  role: 'bot' | 'user'
  text: string
}

export function ChatBubble({ role, text }: ChatBubbleProps) {
  // dir="auto" lets each bubble's own text decide its direction (from its
  // first strong-directional character), independent of the page's overall
  // direction - so an English message stays left-aligned even after the UI
  // language is switched to Hebrew afterward, and vice versa.
  return (
    <div className={`bubble ${role}`} dir="auto">
      {text}
    </div>
  )
}
