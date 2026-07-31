import { useNavigate } from 'react-router-dom'
import { MessagesSquare, Search, Filter } from 'lucide-react'
import PageHeader from '../components/PageHeader.jsx'
import EmptyState from '../components/EmptyState.jsx'

export default function HistoryPage() {
  const navigate = useNavigate()

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-8 py-8">
        <PageHeader
          title="Conversation History"
          description="Past conversations across all experts will appear here, with search, folders, and pinning."
        />

        <div className="card">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
            <div className="flex-1 relative">
              <Search className="w-3.5 h-3.5 text-ink-secondary absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                disabled
                placeholder="Search conversations..."
                className="w-full h-8 pl-8 pr-3 rounded-md border border-border bg-bg text-[12.5px]
                           placeholder:text-ink-secondary/60 disabled:cursor-not-allowed"
              />
            </div>
            <button
              disabled
              className="flex items-center gap-1.5 h-8 px-3 rounded-md border border-border text-[12px]
                         text-ink-secondary/60 cursor-not-allowed"
            >
              <Filter className="w-3.5 h-3.5" />
              Filter
            </button>
          </div>

          <EmptyState
            icon={MessagesSquare}
            title="No conversation history yet"
            description="Conversations aren't persisted between sessions yet — this view is ready for when that's connected."
            action={
              <button
                onClick={() => navigate('/bi-expert')}
                className="text-[12.5px] font-medium text-primary hover:underline"
              >
                Start a conversation →
              </button>
            }
          />
        </div>
      </div>
    </div>
  )
}
