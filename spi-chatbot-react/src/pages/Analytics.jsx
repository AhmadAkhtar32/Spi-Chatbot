import { BarChart3, MessagesSquare, Clock3, TrendingUp } from 'lucide-react'
import PageHeader from '../components/PageHeader.jsx'
import MetricCard from '../components/MetricCard.jsx'
import EmptyState from '../components/EmptyState.jsx'

export default function AnalyticsPage() {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-6xl mx-auto px-8 py-8">
        <PageHeader
          title="Analytics"
          description="Usage, response time, and popular query trends across all experts. Populated once conversation logging is connected."
        />

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-6">
          <MetricCard icon={MessagesSquare} label="Total conversations" value="—" hint="Awaiting data" />
          <MetricCard icon={Clock3} label="Avg. response time" value="—" hint="Awaiting data" />
          <MetricCard icon={TrendingUp} label="Resolution rate" value="—" hint="Awaiting data" />
          <MetricCard icon={BarChart3} label="Most active expert" value="—" hint="Awaiting data" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="card">
            <div className="px-4 py-3 border-b border-border">
              <h2 className="text-[13px] font-semibold text-ink">Usage over time</h2>
            </div>
            <EmptyState
              icon={BarChart3}
              title="No usage data yet"
              description="This chart will populate once conversations are logged."
            />
          </div>
          <div className="card">
            <div className="px-4 py-3 border-b border-border">
              <h2 className="text-[13px] font-semibold text-ink">Popular queries</h2>
            </div>
            <EmptyState
              icon={TrendingUp}
              title="No query data yet"
              description="The most-asked questions across BI, Implementation, and Support Expert will show here."
            />
          </div>
        </div>
      </div>
    </div>
  )
}
