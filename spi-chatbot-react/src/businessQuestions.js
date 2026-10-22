const PREFIX = '/api/demo/business/'

const SEGMENTS = {
  stock: 'stock',
  sales_orders: 'sales-orders',
  purchase_orders: 'purchase-orders',
  payroll: 'payroll',
  tickets: 'tickets',
  credit_return_notes: 'credit-return-notes',
}

const ID_KIND = {
  SO: 'sales_orders',
  PO: 'purchase_orders',
  PAY: 'payroll',
  TCK: 'tickets',
  CRN: 'credit_return_notes',
}

const MONTHS = [
  'january', 'february', 'march', 'april',
  'may', 'june', 'july', 'august',
  'september', 'october', 'november', 'december',
]

const STATUS = {
  sales_orders: [
    'pending approval', 'dispatched', 'delivered', 'processing',
  ],
  purchase_orders: [
    'pending approval', 'approved', 'received', 'ordered',
  ],
  payroll: ['paid', 'unpaid'],
  tickets: ['in progress', 'resolved', 'open'],
  credit_return_notes: ['approved', 'pending approval'],
}

export function isRecordPath(path) {
  return (
    typeof path === 'string'
    && /^\/api\/demo\/business\/(?:stock\/[A-Za-z0-9-]{1,64}\/[A-Za-z0-9-]{1,64}|(?:sales-orders|purchase-orders|credit-return-notes|payroll|tickets)\/[A-Za-z0-9-]{1,64})$/.test(path)
  )
}

const clarify = (message) => ({ clarification: message })
const unique = (values) => [...new Set(values)]

export function planBusinessQuestion(question) {
  const original = String(question || '').trim()

  if (!original || original.length > 2000) {
    return clarify('Enter a question of up to 2,000 characters.')
  }

  if (/^(?:next|next page|previous|previous page)$/i.test(original)) {
    return { page: /^next/i.test(original) ? 1 : -1 }
  }

  const text = original.toLowerCase()

  if (/\b(compare|average|sum|revenue|profit|forecast|trend|chart|top|total amount|total value|total stock)\b/.test(text)) {
    return clarify(
      'This request needs BI access. A licensed user can open the BI expert tab for supported summaries. Revenue, profit and forecasts need additional data and are not available in this demo.'
    )
  }

  if (/\b(not|except|exclude|excluding|without|above|below|greater|less|over|under|last|this|today|yesterday)\b/.test(text)) {
    return clarify(
      'Use a direct record search with explicit dates or a payroll month. Comparisons, exclusions and relative dates are not supported in this step.'
    )
  }

  const upper = original.toUpperCase()

  const ids = unique(
    upper.match(/\b(?:SO|PO|CRN|PAY|TCK)-[A-Z0-9-]+\b/g) || []
  )
  const skus = unique(
    upper.match(/\bSKU-[A-Z0-9-]+\b/g) || []
  )
  const warehouses = unique(
    upper.match(/\bWH-[A-Z0-9-]+\b/g) || []
  )
  const parties = unique(
    upper.match(/\bPARTY-[A-Z0-9-]+\b/g) || []
  )
  const employees = unique(
    upper.match(/\bEMP-[A-Z0-9-]+\b/g) || []
  )

  if (
    [ids, skus, warehouses, parties, employees]
      .some((list) => list.length > 1)
  ) {
    return clarify(
      'Search one record, item, warehouse, party or employee at a time.'
    )
  }

  const kinds = new Set(
    ids.map((id) => ID_KIND[id.split('-')[0]])
  )

  if (
    /\bstock\b/.test(text)
    || (
      /\binventory\b/.test(text)
      && !/\btickets?\b/.test(text)
    )
    || skus.length
    || warehouses.length
  ) {
    kinds.add('stock')
  }

  if (/\b(sales? orders?|sales)\b/.test(text)) {
    kinds.add('sales_orders')
  }

  if (/\b(purchase orders?|purchases?|purchasing)\b/.test(text)) {
    kinds.add('purchase_orders')
  }

  if (/\b(payroll|salary|salaries|payslips?)\b/.test(text)) {
    kinds.add('payroll')
  }

  if (/\b(tickets?)\b/.test(text)) {
    kinds.add('tickets')
  }

  if (/\b(credit[ -]?returns?|credit notes?|return notes?|returns?)\b/.test(text)) {
    kinds.add('credit_return_notes')
  }

  if (kinds.size !== 1) {
    return clarify(
      'Choose one area: stock, sales orders, purchase orders, payroll, tickets or credit returns.'
    )
  }

  const kind = [...kinds][0]

  if (kind !== 'stock' && (skus.length || warehouses.length)) {
    return clarify(
      'Use the stock area for item and warehouse searches.'
    )
  }

  if (employees.length && kind !== 'payroll') {
    return clarify('Employee filtering is available for payroll.')
  }

  if (
    parties.length
    && ![
      'sales_orders',
      'purchase_orders',
      'credit_return_notes',
    ].includes(kind)
  ) {
    return clarify(
      'Party filtering is available for sales, purchases and credit returns.'
    )
  }

  const params = new URLSearchParams({
    limit: '10',
    offset: '0',
  })

  let rest = text

  const dates = unique(
    text.match(/\b\d{4}-\d{2}-\d{2}\b/g) || []
  )

  if (dates.length > 2) {
    return clarify('Use one date or one date range.')
  }

  if (dates.length) {
    if (
      ![
        'sales_orders',
        'purchase_orders',
        'tickets',
        'credit_return_notes',
      ].includes(kind)
    ) {
      return clarify(
        'For payroll, use a month such as September 2026. Stock search has no date filter.'
      )
    }

    params.set('date_from', dates[0])
    params.set('date_to', dates[1] || dates[0])

    for (const value of dates) {
      rest = rest.replaceAll(value, ' ')
    }
  }

  const periods = unique(
    rest.match(/\b\d{4}-\d{2}\b(?!-\d)/g) || []
  )

  const namedMonth = rest.match(
    new RegExp(`\\b(${MONTHS.join('|')})\\s+(\\d{4})\\b`)
  )

  if (namedMonth) {
    const month = String(
      MONTHS.indexOf(namedMonth[1]) + 1
    ).padStart(2, '0')

    periods.push(`${namedMonth[2]}-${month}`)
    rest = rest.replace(namedMonth[0], ' ')
  }

  if (periods.length > 1) {
    return clarify('Use one payroll month per question.')
  }

  if (periods.length) {
    if (kind !== 'payroll') {
      return clarify(
        'Use full YYYY-MM-DD dates for this area.'
      )
    }

    params.set('period', periods[0])
    rest = rest.replaceAll(periods[0], ' ')
  } else if (
    MONTHS.some(
      (month) => new RegExp(`\\b${month}\\b`).test(rest)
    )
  ) {
    return clarify(
      'Include the year with the month, for example September 2026.'
    )
  }

  const statuses = (STATUS[kind] || []).filter(
    (status) => new RegExp(`\\b${status}\\b`).test(rest)
  )

  const pendingAlias = (
    !statuses.length
    && /\bpending\b/.test(rest)
    && (STATUS[kind] || []).includes('pending approval')
  )

  if (pendingAlias) {
    statuses.push('pending approval')
  }

  if (statuses.length > 1) {
    return clarify('Use one status per question.')
  }

  if (statuses.length) {
    params.set('status', statuses[0])
    rest = rest.replaceAll(
      pendingAlias ? 'pending' : statuses[0],
      ' '
    )
  }

  if (kind === 'stock') {
    if (/\b(out of stock|zero stock)\b/.test(rest)) {
      return clarify(
        'Zero-stock filtering is not available in this screen yet. Ask for an item or for available stock.'
      )
    }

    if (/\b(in stock|available|positive stock)\b/.test(rest)) {
      params.set('in_stock_only', 'true')
      rest = rest.replace(
        /\b(in stock|available|positive stock)\b/g,
        ' '
      )
    }

    if (warehouses[0]) {
      params.set('warehouse_id', warehouses[0])
    }

    if (
      !warehouses.length
      && /\b(?:in|at)\s+[a-z]/.test(rest)
    ) {
      return clarify(
        'Use a warehouse code, for example WH-LHR, when specifying a location. Item-name searches can also run across your permitted warehouses.'
      )
    }
  }

  if (parties[0]) {
    params.set('party_id', parties[0])
  }

  if (employees[0]) {
    params.set('employee_id', employees[0])
  }

  if (kind === 'tickets') {
    const modules = rest.match(/\b(financial|inventory)\b/g) || []

    if (modules.length > 1) {
      return clarify('Use one ticket module per question.')
    }

    if (modules[0]) {
      params.set('module', modules[0])
      rest = rest.replaceAll(modules[0], ' ')
    }
  }

  const first = rest.match(/\bfirst\s+(\d+)\b/)

  if (first) {
    const amount = Number(first[1])

    if (amount < 1 || amount > 100) {
      return clarify(
        'Request between 1 and 100 records per page.'
      )
    }

    params.set('limit', String(amount))
    rest = rest.replace(first[0], ' ')
  }

  rest = rest.replace(
    /\b(?:for|of|by)\s+(?:customer|supplier|employee|warehouse|item)\b/g,
    ' '
  )

  if (parties.length) {
    rest = rest.replace(/\b(customer|supplier|party)\b/g, ' ')
  }

  if (employees.length) {
    rest = rest.replace(/\bemployee\b/g, ' ')
  }

  if (warehouses.length) {
    rest = rest.replace(/\bwarehouse\b/g, ' ')
  }

  if (skus.length) {
    rest = rest.replace(/\bitem\b/g, ' ')
  }

  for (const value of [
    ...ids,
    ...skus,
    ...warehouses,
    ...parties,
    ...employees,
  ]) {
    rest = rest.replaceAll(value.toLowerCase(), ' ')
  }

  rest = rest.replace(
    /\b(sales? orders?|purchase orders?|credit[ -]?returns?|credit notes?|return notes?)\b/g,
    ' '
  )

  rest = rest.replace(
    /\b(show|list|find|search|get|check|tell|me|please|what|which|is|are|the|a|an|of|for|in|at|on|from|to|between|and|with|by|all|my|our|status|stock|inventory|sales|purchase|purchases|purchasing|payroll|salary|salaries|payslip|payslips|ticket|tickets|returns|records|details|only|how|many|count|total)\b/g,
    ' '
  )

  rest = rest
    .replace(/[?.,!"']/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  if (rest.length > 100) {
    return clarify(
      'Use an item, party or employee search phrase of up to 100 characters.'
    )
  }

  const hasFilters = [...params.keys()].some(
    (key) => !['limit', 'offset'].includes(key)
  )

  if (ids[0] && !hasFilters && !rest) {
    return {
      path: `${PREFIX}${SEGMENTS[kind]}/${ids[0]}`,
      kind,
    }
  }

  if (
    kind === 'stock'
    && skus[0]
    && warehouses[0]
    && !params.has('in_stock_only')
    && !rest
  ) {
    return {
      path: `${PREFIX}stock/${skus[0]}/${warehouses[0]}`,
      kind,
    }
  }

  const q = [ids[0] || skus[0], rest]
    .filter(Boolean)
    .join(' ')

  if (q.length > 100) {
    return clarify(
      'Shorten the record search phrase to 100 characters.'
    )
  }

  if (q) {
    params.set('q', q)
  }

  return {
    path: `${PREFIX}${SEGMENTS[kind]}?${params}`,
    kind,
  }
}

export function pagePath(context, direction) {
  if (!context) {
    return clarify(
      'Run a search first, then ask for the next or previous page.'
    )
  }

  const params = new URLSearchParams(
    context.path.split('?')[1]
  )

  const offset = Number(context.result.offset)
  const limit = Number(context.result.limit)

  if (
    ![offset, limit].every(Number.isSafeInteger)
    || limit < 1
  ) {
    return clarify(
      'Run the search again before changing pages.'
    )
  }

  if (direction > 0 && !context.result.has_more) {
    return clarify('There are no more matching records.')
  }

  if (direction < 0 && offset === 0) {
    return clarify('You are already on the first page.')
  }

  params.set(
    'offset',
    String(Math.max(0, offset + direction * limit))
  )

  return {
    path: `${context.path.split('?')[0]}?${params}`,
    kind: context.result.kind,
  }
}

const safe = (value) => String(value ?? 'Unavailable')
  .replace(/[\\`*_{}\[\]()<>#!|]/g, '\\$&')
  .replace(/[\r\n]+/g, ' ')

const money = (value) => Number.isFinite(value)
  ? new Intl.NumberFormat('en-PK').format(value)
  : 'Unavailable'

function recordText(kind, record, details = {}) {
  switch (kind) {
    case 'stock':
      return `${safe(details.item_name || record.item_id)} (${safe(record.item_id)}) in ${safe(details.warehouse_name || record.warehouse_id)}: **${safe(record.quantity_available)} ${safe(details.unit || 'units')} available**.`

    case 'sales_orders':
      return `Sales order **${safe(record.id)}**: **${safe(record.status)}**. Customer: ${safe(details.party_name || record.customer_party_id)} (${safe(record.customer_party_id)}). Total: PKR ${money(record.total_amount_pkr)}.`

    case 'purchase_orders':
      return `Purchase order **${safe(record.id)}**: **${safe(record.status)}**. Supplier: ${safe(details.party_name || record.supplier_party_id)} (${safe(record.supplier_party_id)}). Total: PKR ${money(record.total_amount_pkr)}.`

    case 'credit_return_notes':
      return `Credit return **${safe(record.id)}**: **${safe(record.status)}**. Sales order: ${safe(record.sales_order_id)}. Customer: ${safe(details.party_name || record.customer_party_id)}. Credit: PKR ${money(record.credit_amount_pkr)}.`

    case 'payroll':
      return `Payroll **${safe(record.id)}** for ${safe(details.employee_name || record.employee_id)} (${safe(record.employee_id)}), ${safe(record.period)}: **${safe(record.status)}**. Net pay: PKR ${money(record.net)}.`

    case 'tickets':
      return `Ticket **${safe(record.id)}**: **${safe(record.status)}**. Module: ${safe(record.module)}. Subject: ${safe(record.subject)}.`

    default:
      throw new Error('Unsupported business response.')
  }
}

export function businessAnswer(result) {
  const source = (
    `\n\nFictional demo snapshot: ${safe(result.snapshot_at)}.`
  )

  if (result.record) {
    return recordText(
      result.kind,
      result.record,
      result.details
    ) + source
  }

  if (
    !Array.isArray(result.items)
    || !Number.isSafeInteger(result.total)
  ) {
    throw new Error('Invalid business response.')
  }

  if (!result.items.length) {
    return (
      'No matching records were found within your permitted access.'
      + source
    )
  }

  const label = result.kind === 'stock'
    ? 'stock rows (item and warehouse pairs)'
    : 'records'

  const lines = result.items.map(
    (item) => `- ${recordText(
      result.kind,
      item.record,
      item.details
    )}`
  )

  const paging = result.has_more
    ? 'Ask "next page" to continue.'
    : 'End of matching results.'

  return (
    `**${result.total} matching ${label}** within your permitted access. `
    + `Showing ${result.offset + 1}-${result.offset + result.items.length}.`
    + `\n\n${lines.join('\n')}\n\n${paging}${source}`
  )
}