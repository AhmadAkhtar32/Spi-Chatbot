import { HelpCircle } from 'lucide-react'
import PageHeader from '../components/PageHeader.jsx'
import EmptyState from '../components/EmptyState.jsx'

export default function HelpPage() {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-8 py-8">
        <PageHeader title="Help" description="Documentation and support resources." />
        <div className="card">
          <EmptyState
            icon={HelpCircle}
            title="Help center coming soon"
            description="Documentation for each expert, keyboard shortcuts, and support contact will live here."
          />
        </div>
      </div>
    </div>
  )
}
