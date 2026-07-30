function getGreeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good Morning'
  if (hour < 17) return 'Good Afternoon'
  return 'Good Evening'
}

export default function WelcomeSection() {
  return (
    <div className="mb-8">
      <h1 className="text-[26px] font-semibold text-[#111827] mb-1.5 tracking-tight">
        {getGreeting()} <span aria-hidden>👋</span>
      </h1>
      <p className="text-[15px] text-[#111827] font-medium mb-1">Welcome to SPI AI Assistant</p>
      <p className="text-[14px] text-[#6B7280] leading-relaxed max-w-2xl">
        I can help you search ERP data, check inventory, track orders, navigate ERP screens,
        generate reports, and answer business questions.
      </p>
    </div>
  )
}
