import { FileText, Download } from 'lucide-react'
import PageHeader from '../components/PageHeader.jsx'
import EmptyState from '../components/EmptyState.jsx'

export default function ReportsPage() {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-6xl mx-auto px-8 py-8">
        <PageHeader
          title="Reports"
          description="Generated and exported reports across ERP modules will be listed here."
          action={
            <button
              disabled
              className="flex items-center gap-1.5 h-9 px-3.5 rounded-md border border-border text-[12.5px]
                         text-ink-secondary/60 cursor-not-allowed"
            >
              <Download className="w-3.5 h-3.5" />
              Export
            </button>
          }
        />

        <div className="card overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border bg-bg">
                <th className="text-left font-semibold text-ink-secondary px-4 py-2.5">Report</th>
                <th className="text-left font-semibold text-ink-secondary px-4 py-2.5">Module</th>
                <th className="text-left font-semibold text-ink-secondary px-4 py-2.5">Generated</th>
                <th className="text-left font-semibold text-ink-secondary px-4 py-2.5">Format</th>
              </tr>
            </thead>
          </table>
          <EmptyState
            icon={FileText}
            title="No reports generated yet"
            description="This is planned for the Document Generator expert — reports will appear here once that's connected."
          />
        </div>
      </div>
    </div>
  )
}
