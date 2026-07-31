import { User, Shield, Bell, Globe, Palette, Plug, Activity, Info } from 'lucide-react'
import PageHeader from '../components/PageHeader.jsx'

const SECTIONS = [
  { icon: User, title: 'Profile', description: 'Name, role, department, organization.' },
  { icon: Shield, title: 'Security', description: 'Password, sessions, two-factor authentication.' },
  { icon: Bell, title: 'Notifications', description: 'Email and in-app notification preferences.' },
  { icon: Globe, title: 'Language', description: 'Interface language and regional format.' },
  { icon: Palette, title: 'Appearance', description: 'Light mode only, for now.' },
  { icon: Plug, title: 'Integrations', description: 'Connected services and API keys.' },
  { icon: Activity, title: 'API Status', description: 'Live status of Gemini, function calling, and RAG.' },
  { icon: Shield, title: 'Licensing', description: 'Per-client module entitlements — planned.' },
  { icon: Info, title: 'About', description: 'Version, build info, and support contact.' },
]

export default function SettingsPage() {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-8 py-8">
        <PageHeader title="Settings" description="Manage your account, integrations, and preferences." />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
          {SECTIONS.map((s) => (
            <button
              key={s.title}
              disabled
              className="text-left card p-4 opacity-80 cursor-not-allowed"
            >
              <div className="flex items-center gap-2.5 mb-1.5">
                <span className="flex items-center justify-center w-7 h-7 rounded-md bg-slate-100">
                  <s.icon className="w-3.5 h-3.5 text-ink-secondary" strokeWidth={2} />
                </span>
                <h3 className="text-[13.5px] font-semibold text-ink">{s.title}</h3>
              </div>
              <p className="text-[12px] text-ink-secondary leading-relaxed">{s.description}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
