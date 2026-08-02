import { useNavigate } from 'react-router-dom'
import {
  MessageSquareText,
  Wrench,
  LifeBuoy,
  FolderOpen,
  FileText,
  PackageSearch,
  ClipboardList,
  Compass,
  BarChart3,
  MessagesSquare,
} from 'lucide-react'
import SuggestionChip from '../components/SuggestionChip.jsx'
import EmptyState from '../components/EmptyState.jsx'

function getGreeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

const MODULES = [
  {
    key: 'bi-expert',
    icon: MessageSquareText,
    iconBg: 'bg-primary/10',
    iconColor: 'text-primary',
    title: 'BI Expert',
    description: 'Stock, order status, and ERP navigation — answered live.',
    to: '/bi-expert',
  },
  {
    key: 'implementation-expert',
    icon: Wrench,
    iconBg: 'bg-primary/10',
    iconColor: 'text-primary',
    title: 'Implementation Expert',
    description: 'Setup, configuration guidance, and gap analysis.',
    to: '/implementation-expert',
  },
  {
    key: 'support-expert',
    icon: LifeBuoy,
    iconBg: 'bg-primary/10',
    iconColor: 'text-primary',
    title: 'Support Expert',
    description: 'Incident analysis and root-cause troubleshooting.',
    to: '/support-expert',
  },
  {
    key: 'project-knowledge',
    icon: FolderOpen,
    iconBg: 'bg-primary/10',
    iconColor: 'text-primary',
    title: 'Project Knowledge Expert',
    description: 'Customer-specific documents, decisions, and history.',
    to: '/project-knowledge-expert',
  },
  {
    key: 'document-generator',
    icon: FileText,
    iconBg: 'bg-primary/10',
    iconColor: 'text-primary',
    title: 'Document Generator',
    description: 'Consistent, template-based deliverables.',
    to: '/document-generator',
  },
]

const RECOMMENDED_PROMPTS = [
  { icon: PackageSearch, label: 'Check stock availability', prompt: "What's the stock of Pepsi?" },
  { icon: ClipboardList, label: 'Order status', prompt: "What's the status of order #1234?" },
  { icon: Compass, label: 'Find Purchase Order screen', prompt: 'Where do I create a purchase order?' },
  { icon: BarChart3, label: 'Inventory report', prompt: 'Show me the inventory stock report' },
]

export default function Dashboard() {
  const navigate = useNavigate()

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-8 py-8">
        {/* Welcome */}
        <div className="mb-8">
          <h1 className="text-[22px] font-semibold text-ink mb-1 tracking-tight">
            {getGreeting()}, Minahil
          </h1>
          <p className="text-[13.5px] text-ink-secondary max-w-2xl leading-relaxed">
            Ask ERP data questions, get implementation guidance, troubleshoot issues, search your
            project's documents, or generate a Purchase Order — all five experts are live.
          </p>
        </div>

        <section className="mb-8">
          <h2 className="text-[13px] font-semibold text-ink mb-3">Experts &amp; modules</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {MODULES.map((m) => (
              <button
                key={m.key}
                onClick={() => navigate(m.to)}
                className="group text-left card-interactive p-4 cursor-pointer"
              >
                <div className="flex items-start justify-between mb-2.5">
                  <span className={`flex items-center justify-center w-8 h-8 rounded-md ${m.iconBg}`}>
                    <m.icon className={`w-4 h-4 ${m.iconColor}`} strokeWidth={2} />
                  </span>
                  <span className="text-[9.5px] font-semibold tracking-wide text-success bg-success/10 rounded px-1.5 py-0.5">
                    LIVE
                  </span>
                </div>
                <h3 className="text-[13.5px] font-semibold text-ink mb-1">{m.title}</h3>
                <p className="text-[12px] text-ink-secondary leading-relaxed">{m.description}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="mb-8">
          <h2 className="text-[13px] font-semibold text-ink mb-3">Recommended prompts</h2>
          <div className="flex flex-wrap gap-2">
            {RECOMMENDED_PROMPTS.map((p) => (
              <SuggestionChip
                key={p.label}
                icon={p.icon}
                label={p.label}
                onClick={() => navigate('/bi-expert')}
              />
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-[13px] font-semibold text-ink mb-3">Recent activity</h2>
          <div className="card">
            <EmptyState
              icon={MessagesSquare}
              title="No conversations yet"
              description="Start a conversation with any expert and it will show up here for quick access later."
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
        </section>
      </div>
    </div>
  )
}
