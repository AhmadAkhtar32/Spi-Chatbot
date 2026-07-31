import { useNavigate } from 'react-router-dom'
import {
  MessageSquareText,
  Wrench,
  LifeBuoy,
  FolderOpen,
  FileText,
  ShieldCheck,
  PackageSearch,
  ClipboardList,
  Compass,
  BarChart3,
  MessagesSquare,
  Clock3,
  Sparkles,
  Megaphone,
  History,
} from 'lucide-react'
import MetricCard from '../components/MetricCard.jsx'
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
    status: 'active',
  },
  {
    key: 'implementation-expert',
    icon: Wrench,
    iconBg: 'bg-primary/10',
    iconColor: 'text-primary',
    title: 'Implementation Expert',
    description: 'Setup, configuration guidance, and gap analysis.',
    to: '/implementation-expert',
    status: 'active',
  },
  {
    key: 'support-expert',
    icon: LifeBuoy,
    iconBg: 'bg-primary/10',
    iconColor: 'text-primary',
    title: 'Support Expert',
    description: 'Incident analysis and root-cause troubleshooting.',
    to: '/support-expert',
    status: 'active',
  },
  {
    key: 'project-knowledge',
    icon: FolderOpen,
    iconBg: 'bg-slate-100',
    iconColor: 'text-ink-secondary',
    title: 'Project Knowledge Expert',
    description: 'Customer-specific documents, decisions, and history.',
    to: null,
    status: 'planned',
  },
  {
    key: 'document-generator',
    icon: FileText,
    iconBg: 'bg-slate-100',
    iconColor: 'text-ink-secondary',
    title: 'Document Generator',
    description: 'Consistent, template-based deliverables.',
    to: null,
    status: 'planned',
  },
  {
    key: 'licensing',
    icon: ShieldCheck,
    iconBg: 'bg-slate-100',
    iconColor: 'text-ink-secondary',
    title: 'Licensing &amp; Entitlement',
    description: 'Per-client module and feature access control.',
    to: null,
    status: 'planned',
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
      <div className="max-w-6xl mx-auto px-8 py-8">
        {/* Welcome */}
        <div className="mb-7">
          <h1 className="text-[22px] font-semibold text-ink mb-1 tracking-tight">
            {getGreeting()}, Minahil
          </h1>
          <p className="text-[13.5px] text-ink-secondary max-w-2xl leading-relaxed">
            Ask ERP data questions, get implementation guidance, or troubleshoot issues — all from
            one assistant. BI Expert is live; Implementation and Support experts are being
            connected next.
          </p>
        </div>

        {/* KPI row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-7">
          <MetricCard icon={MessagesSquare} label="Conversations today" value="12" hint="+4 vs. yesterday" />
          <MetricCard icon={Clock3} label="Avg. response time" value="1.8s" hint="Across all experts" />
          <MetricCard icon={Sparkles} label="Active experts" value="3 / 3" hint="All experts live" />
          <MetricCard icon={History} label="Queries resolved" value="47" hint="Last 7 days" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Left: modules + recommended prompts */}
          <div className="lg:col-span-2 flex flex-col gap-6">
            <section>
              <h2 className="text-[13px] font-semibold text-ink mb-3">Experts &amp; modules</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {MODULES.map((m) => (
                  <button
                    key={m.key}
                    onClick={() => m.to && navigate(m.to)}
                    disabled={!m.to}
                    className={`group text-left p-4 transition-all
                      ${m.to ? 'card-interactive cursor-pointer' : 'card cursor-default opacity-70'}`}
                  >
                    <div className="flex items-start justify-between mb-2.5">
                      <span className={`flex items-center justify-center w-8 h-8 rounded-md ${m.iconBg}`}>
                        <m.icon className={`w-4 h-4 ${m.iconColor}`} strokeWidth={2} />
                      </span>
                      {m.status === 'active' && (
                        <span className="text-[9.5px] font-semibold tracking-wide text-success bg-success/10 rounded px-1.5 py-0.5">
                          LIVE
                        </span>
                      )}
                      {m.status === 'soon' && (
                        <span className="text-[9.5px] font-semibold tracking-wide text-primary bg-primary/8 rounded px-1.5 py-0.5">
                          SOON
                        </span>
                      )}
                      {m.status === 'planned' && (
                        <span className="text-[9.5px] font-semibold tracking-wide text-ink-secondary bg-slate-100 rounded px-1.5 py-0.5">
                          PLANNED
                        </span>
                      )}
                    </div>
                    <h3 className="text-[13.5px] font-semibold text-ink mb-1">{m.title}</h3>
                    <p className="text-[12px] text-ink-secondary leading-relaxed">{m.description}</p>
                  </button>
                ))}
              </div>
            </section>

            <section>
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
                  description="Start a conversation with BI Expert and it will show up here for quick access later."
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

          {/* Right: announcements + license status */}
          <div className="flex flex-col gap-5">
            <section className="card p-4">
              <div className="flex items-center gap-2 mb-3">
                <Megaphone className="w-3.5 h-3.5 text-ink-secondary" strokeWidth={2} />
                <h2 className="text-[12.5px] font-semibold text-ink">Announcements</h2>
              </div>
              <div className="space-y-3">
                <div className="text-[12.5px] text-ink leading-relaxed pb-3 border-b border-border">
                  <span className="font-medium">Conversation memory added.</span> Follow-up
                  questions (e.g. "what about Coke?") now resolve correctly within BI Expert.
                </div>
                <div className="text-[12.5px] text-ink leading-relaxed">
                  <span className="font-medium">Two new experts are live.</span>{' '}
                  Implementation and Support Expert now have full chat interfaces, answering from
                  real reference documents.
                </div>
              </div>
            </section>

            <section className="card p-4">
              <div className="flex items-center gap-2 mb-3">
                <ShieldCheck className="w-3.5 h-3.5 text-ink-secondary" strokeWidth={2} />
                <h2 className="text-[12.5px] font-semibold text-ink">License status</h2>
              </div>
              <div className="text-[12px] text-ink-secondary leading-relaxed mb-3">
                Per-client entitlement system not yet configured. All experts shown here are
                currently unrestricted in this environment.
              </div>
              <div className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-ink-secondary bg-slate-100 rounded-full px-2.5 py-1">
                Licensing — planned
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}
