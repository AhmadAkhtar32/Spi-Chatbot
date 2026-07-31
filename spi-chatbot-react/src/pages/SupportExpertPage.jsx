import { AlertOctagon, Search, Clock, Printer } from 'lucide-react'
import ExpertChatPage from './ExpertChatPage.jsx'

const SUGGESTIONS = [
  { icon: AlertOctagon, label: 'Random logouts', prompt: 'Why would users get logged out randomly?' },
  { icon: Search, label: 'Report generation failing', prompt: 'A report is returning blank results even though data exists — why?' },
  { icon: Clock, label: 'Slow performance', prompt: 'Why does the system get slow during month-end close?' },
  { icon: Printer, label: 'Barcode printing issues', prompt: 'Barcode labels are printing garbled — what could cause that?' },
]

export default function SupportExpertPage() {
  return (
    <ExpertChatPage
      title="Support Expert"
      description="Incident analysis, troubleshooting, and root cause suggestions — answered from real support documentation."
      breadcrumb={['Dashboard', 'Support Expert']}
      endpoint="/api/support-expert"
      suggestions={SUGGESTIONS}
    />
  )
}
