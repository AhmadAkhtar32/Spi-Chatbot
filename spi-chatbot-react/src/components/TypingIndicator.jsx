export default function TypingIndicator() {
  return (
    <div className="flex justify-start animate-fade-in">
      <div className="bg-surface border border-border rounded-lg px-4 py-3 flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-ink-secondary/50 animate-pulse [animation-delay:0ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-ink-secondary/50 animate-pulse [animation-delay:150ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-ink-secondary/50 animate-pulse [animation-delay:300ms]" />
      </div>
    </div>
  )
}
