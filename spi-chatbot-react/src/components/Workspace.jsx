import { motion } from 'framer-motion'
import { PackageSearch, ShoppingCart, ClipboardList, Wallet, Users, Compass } from 'lucide-react'
import WelcomeSection from './WelcomeSection.jsx'
import ModuleCard from './ModuleCard.jsx'
import PopularTask from './PopularTask.jsx'

const MODULES = [
  {
    key: 'inventory',
    icon: PackageSearch,
    iconBg: '#DBEAFE',
    iconColor: '#2563EB',
    title: 'Inventory',
    items: ['Check stock availability', 'Locate warehouse inventory', 'View stock reports'],
    prompt: 'Give me an overview of what you can help with in the Inventory module.',
  },
  {
    key: 'sales',
    icon: ShoppingCart,
    iconBg: '#DCFCE7',
    iconColor: '#16A34A',
    title: 'Sales',
    items: ['Track customer orders', 'Invoices', 'Delivery status'],
    prompt: 'Give me an overview of what you can help with in the Sales module.',
  },
  {
    key: 'purchase',
    icon: ClipboardList,
    iconBg: '#F3E8FF',
    iconColor: '#7C3AED',
    title: 'Purchase',
    items: ['Purchase Orders', 'Supplier information', 'GRNs'],
    prompt: 'Give me an overview of what you can help with in the Purchase module.',
  },
  {
    key: 'finance',
    icon: Wallet,
    iconBg: '#FEF3C7',
    iconColor: '#D97706',
    title: 'Finance',
    items: ['Balances', 'Payments', 'Reports'],
    prompt: 'Give me an overview of what you can help with in the Finance module.',
  },
  {
    key: 'payroll',
    icon: Users,
    iconBg: '#E0E7FF',
    iconColor: '#4F46E5',
    title: 'Payroll',
    items: ['Salary', 'Attendance', 'Employees'],
    prompt: 'Give me an overview of what you can help with in the Payroll module.',
  },
  {
    key: 'navigation',
    icon: Compass,
    iconBg: '#F1F5F9',
    iconColor: '#475569',
    title: 'ERP Navigation',
    items: ['Find screens', 'Locate menus', 'Business workflows'],
    prompt: 'Help me navigate the ERP — what screens and menus are available?',
  },
]

const POPULAR_TASKS = [
  'Check Pepsi stock',
  'Find Purchase Order screen',
  'Where is Sales Return?',
  'Generate Inventory Report',
  'Track Order #10234',
]

export default function Workspace({ onModuleSelect, onTaskSelect }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.22, ease: 'easeOut' }}
      className="flex-1 overflow-y-auto"
    >
      <div className="max-w-5xl mx-auto px-8 py-9">
        <WelcomeSection />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          {MODULES.map((m) => (
            <ModuleCard
              key={m.key}
              icon={m.icon}
              iconBg={m.iconBg}
              iconColor={m.iconColor}
              title={m.title}
              items={m.items}
              onClick={() => onModuleSelect(m.title, m.prompt)}
            />
          ))}
        </div>

        <div className="bg-white border border-[#D1D5DB] rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-[#D1D5DB]">
            <h2 className="text-[13px] font-semibold text-[#111827]">Popular Tasks</h2>
          </div>
          <div className="py-1.5">
            {POPULAR_TASKS.map((task) => (
              <PopularTask key={task} label={task} onClick={() => onTaskSelect(task)} />
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  )
}
