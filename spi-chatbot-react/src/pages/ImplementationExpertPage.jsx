import { Settings2, ClipboardCheck, FileSearch, AlertTriangle } from 'lucide-react'
import ExpertChatPage from './ExpertChatPage.jsx'

const SUGGESTIONS = [
  { icon: Settings2, label: 'Inventory setup steps', prompt: 'How do I configure the Inventory warehouse hierarchy?' },
  { icon: AlertTriangle, label: 'Common go-live gaps', prompt: "What's the biggest gap we usually find during Inventory go-live?" },
  { icon: FileSearch, label: 'Payroll prerequisites', prompt: 'What has to be configured before Payroll setup can start?' },
  { icon: ClipboardCheck, label: 'Go-live checklist', prompt: 'What should be checked before Inventory go-live?' },
]

export default function ImplementationExpertPage() {
  return (
    <ExpertChatPage
      title="Implementation Expert"
      description="Setup & configuration guidance, gap analysis — answered from real ERP implementation documentation."
      breadcrumb={['Dashboard', 'Implementation Expert']}
      endpoint="/api/implementation-expert"
      suggestions={SUGGESTIONS}
    />
  )
}
