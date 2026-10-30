import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { BarChart3, RotateCw } from 'lucide-react'
import AnimatedBackground from '../components/AnimatedBackground.jsx'
import SuggestionChip from '../components/SuggestionChip.jsx'
import { API_BASE } from '../api/client.js'

const AREAS = {
  sales: 'Sales orders',
  purchases: 'Purchase orders',
  stock: 'Stock',
}

const empty = (area = 'sales') => ({
  area,
  date_from: '',
  date_to: '',
  status: '',
  party_id: '',
  warehouse_id: '',
})

const display = (value) => Number.isFinite(Number(value))
  ? Number(value).toLocaleString('en-PK', {
    maximumFractionDigits: 2,
  })
  : String(value ?? '')

function ReportTable({ title, rows, stock = false }) {
  if (!rows?.length) return null

  const maximum = Math.max(
    1,
    ...rows.map((row) => Number(
      stock ? row.unavailable : row.order_value_pkr
    ))
  )

  return (
    <section className="card p-4 min-w-0">
      <h3 className="font-semibold text-sm mb-3">{title}</h3>

      <div className="space-y-3">
        {rows.map((row) => {
          const value = Number(
            stock ? row.unavailable : row.order_value_pkr
          )

          return (
            <div key={row.id}>
              <div className="flex justify-between gap-3 text-xs mb-1">
                <span className="break-words">
                  {row.label}
                  {row.id !== row.label ? ` (${row.id})` : ''}
                </span>
                <span className="shrink-0">
                  {stock
                    ? `${value} unavailable / ${row.count} rows`
                    : `PKR ${display(row.order_value_pkr)} · ${row.count} orders`}
                </span>
              </div>

              <div
                className="h-2 bg-primary/10 rounded-full overflow-hidden"
                role="img"
                aria-label={`${row.label}: ${value}`}
              >
                <div
                  className="h-full bg-primary rounded-full"
                  style={{
                    width: `${Math.max(0, value) / maximum * 100}%`,
                  }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

export default function BIPage() {
  const {
    assistantSession,
    conversationId,
    switchAssistantUser,
  } = useOutletContext()

  const [form, setForm] = useState(empty())
  const [options, setOptions] = useState(null)
  const [report, setReport] = useState(null)
  const [view, setView] = useState('summary')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)

  const requestRef = useRef(null)
  const keyRef = useRef('')

  const key = `${assistantSession?.token || ''}:${conversationId || ''}`
  keyRef.current = key

  useEffect(() => {
    const controller = new AbortController()

    requestRef.current?.abort()
    requestRef.current = null
    setReport(null)
    setOptions(null)
    setBusy(false)
    setError('')

    fetch(`${API_BASE}/api/v1/business/bi/suggestions`, {
      headers: {
        Authorization: `Bearer ${assistantSession.token}`,
      },
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (
          controller.signal.aborted
          || keyRef.current !== key
        ) {
          return null
        }

        if (response.status === 401) {
          switchAssistantUser(
            'Sample session expired. Enter the presenter PIN again.'
          )
          return null
        }

        if (response.status === 403) {
          throw new Error(
            'BI is unavailable to this user or session mode.'
          )
        }

        if (!response.ok) {
          throw new Error(
            `Could not load BI reports (${response.status}).`
          )
        }

        return response.json()
      })
      .then((data) => {
        if (
          !data
          || controller.signal.aborted
          || keyRef.current !== key
        ) {
          return
        }

        setOptions(data)
        setForm(
          empty(data.available_areas?.[0] || 'sales')
        )
      })
      .catch((reason) => {
        if (
          !controller.signal.aborted
          && keyRef.current === key
        ) {
          setError(reason.message)
        }
      })

    return () => {
      controller.abort()
      requestRef.current?.abort()
      requestRef.current = null
    }
  }, [key, refresh])

  function update(name, value) {
    setForm((previous) => ({
      ...previous,
      [name]: value,
    }))
  }

  async function load(values, nextView = 'summary') {
    if (
      requestRef.current
      || !options?.available_areas?.includes(values.area)
    ) {
      return
    }

    const controller = new AbortController()
    requestRef.current = controller
    const currentKey = key

    setBusy(true)
    setError('')
    setReport(null)
    setForm({
      ...empty(values.area),
      ...values,
    })
    setView(nextView)

    const params = new URLSearchParams({
      area: values.area,
    })

    const fields = values.area === 'stock'
      ? ['warehouse_id']
      : ['date_from', 'date_to', 'status', 'party_id']

    for (const field of fields) {
      if (values[field]?.trim()) {
        params.set(field, values[field].trim())
      }
    }

    const timer = setTimeout(
      () => controller.abort(),
      30000
    )

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/business/bi/summary?${params}`,
        {
          headers: {
            Authorization: `Bearer ${assistantSession.token}`,
          },
          cache: 'no-store',
          signal: controller.signal,
        }
      )

      if (
        controller.signal.aborted
        || keyRef.current !== currentKey
      ) {
        return
      }

      if (response.status === 401) {
        switchAssistantUser(
          'Sample session expired. Enter the presenter PIN again.'
        )
        return
      }

      if (response.status === 403) {
        throw new Error(
          'This BI area is not licensed for your user.'
        )
      }

      if (response.status === 422) {
        throw new Error(
          'Check the filters and date range. Use a valid party or warehouse code.'
        )
      }

      if (!response.ok) {
        throw new Error(
          `BI service is unavailable (${response.status}).`
        )
      }

      const data = await response.json()

      if (
        !controller.signal.aborted
        && keyRef.current === currentKey
      ) {
        setReport(data)
      }
    } catch (reason) {
      if (
        keyRef.current === currentKey
        && requestRef.current === controller
      ) {
        setError(
          reason.name === 'AbortError'
            ? 'The request timed out. Try again.'
            : reason.message
        )
      }
    } finally {
      clearTimeout(timer)

      if (requestRef.current === controller) {
        requestRef.current = null
        setBusy(false)
      }
    }
  }

  const inputClass = (
    'w-full mt-1 rounded-lg border border-border '
    + 'bg-bg px-3 py-2 text-sm'
  )

  const filterLabels = {
    date_from: 'From',
    date_to: 'To',
    status: 'Status',
    party_id: 'Party',
    warehouse_id: 'Warehouse',
  }

  return (
    <div className="flex-1 relative overflow-y-auto">
      <AnimatedBackground />

      <div className="relative z-10 max-w-5xl mx-auto px-6 py-6 space-y-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-primary">
              BI expert
            </h1>
            <p className="text-sm text-ink-secondary mt-1">
              Analyze permitted records from the fictional sample snapshot.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setRefresh((value) => value + 1)}
            className="text-xs text-primary inline-flex gap-1 items-center"
          >
            <RotateCw className="w-3 h-3" />
            Refresh
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {(options?.suggestions || []).map((item) => (
            <SuggestionChip
              key={`${item.area}:${item.view}:${item.filters?.party_id || ''}`}
              icon={BarChart3}
              label={item.question}
              description="Based on your permitted data"
              category={AREAS[item.area]}
              onClick={() => load(
                {
                  ...empty(item.area),
                  ...item.filters,
                },
                item.view
              )}
            />
          ))}
        </div>

        {!options && !error && (
          <p
            role="status"
            className="text-sm text-ink-secondary"
          >
            Checking available BI reports…
          </p>
        )}

        {options && (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              load(form)
            }}
            className="card p-4"
          >
            <fieldset
              disabled={busy}
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
            >
              <label className="text-xs font-medium">
                Data area
                <select
                  className={inputClass}
                  value={form.area}
                  onChange={(event) => {
                    setForm(empty(event.target.value))
                    setReport(null)
                  }}
                >
                  {options.available_areas.map((area) => (
                    <option key={area} value={area}>
                      {AREAS[area]}
                    </option>
                  ))}
                </select>
              </label>

              {form.area === 'stock' ? (
                <label className="text-xs font-medium">
                  Warehouse code
                  <input
                    className={inputClass}
                    value={form.warehouse_id}
                    onChange={(event) => update(
                      'warehouse_id',
                      event.target.value
                    )}
                    placeholder="All permitted warehouses"
                  />
                </label>
              ) : (
                <>
                  <label className="text-xs font-medium">
                    From date
                    <input
                      type="date"
                      className={inputClass}
                      value={form.date_from}
                      onChange={(event) => update(
                        'date_from',
                        event.target.value
                      )}
                    />
                  </label>

                  <label className="text-xs font-medium">
                    To date
                    <input
                      type="date"
                      className={inputClass}
                      value={form.date_to}
                      onChange={(event) => update(
                        'date_to',
                        event.target.value
                      )}
                    />
                  </label>

                  <label className="text-xs font-medium">
                    Customer / supplier code
                    <input
                      className={inputClass}
                      value={form.party_id}
                      onChange={(event) => update(
                        'party_id',
                        event.target.value
                      )}
                      placeholder="All permitted parties"
                    />
                  </label>

                  <label className="text-xs font-medium">
                    Order status
                    <input
                      className={inputClass}
                      value={form.status}
                      onChange={(event) => update(
                        'status',
                        event.target.value
                      )}
                      placeholder="All statuses"
                    />
                  </label>
                </>
              )}
            </fieldset>

            <button
              disabled={
                busy || !options.available_areas.length
              }
              className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {busy ? 'Calculating…' : 'Analyze records'}
            </button>
          </form>
        )}

        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}

        {report && (
          <>
            <h2 className="font-semibold">
              {AREAS[report.area]} · within your permitted access
            </h2>

            <p className="text-xs text-ink-secondary">
              Applied filters:{' '}
              {Object.entries(report.filters || {})
                .filter(
                  ([name, value]) => (
                    name !== 'area'
                    && value !== null
                    && value !== ''
                  )
                )
                .map(
                  ([name, value]) => (
                    `${filterLabels[name]}: ${value}`
                  )
                )
                .join(' · ') || 'All permitted records'}
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {report.metrics.map((metric) => (
                <div
                  key={metric.label}
                  className="card p-4"
                >
                  <p className="text-xs text-ink-secondary">
                    {metric.label}
                  </p>
                  <p className="text-2xl font-semibold mt-2">
                    {display(metric.value)}
                  </p>
                  <p className="text-xs text-ink-secondary mt-1">
                    {metric.unit}
                  </p>
                </div>
              ))}
            </div>

            {report.record_count === 0 && (
              <p className="text-sm text-ink-secondary">
                No matching records within your permitted access.
              </p>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {['status', 'monthly', 'parties']
                .filter(
                  (group) => (
                    view === 'summary' || view === group
                  )
                )
                .map((group) => (
                  <ReportTable
                    key={group}
                    title={{
                      status: 'Order value by status',
                      monthly: 'Order value by month',
                      parties: 'Top five parties by order value',
                    }[group]}
                    rows={report.tables[group]}
                  />
                ))}

              {(view === 'summary' || view === 'warehouses') && (
                <ReportTable
                  title="Unavailable stock by warehouse"
                  rows={report.tables.warehouses}
                  stock
                />
              )}

              {(view === 'summary' || view === 'units')
                && report.tables.units?.length > 0
                && (
                  <section className="card p-4">
                    <h3 className="font-semibold text-sm mb-3">
                      Available quantity by unit
                    </h3>

                    {report.tables.units.map((row) => (
                      <div
                        key={row.label}
                        className="flex justify-between text-sm py-2 border-b border-border"
                      >
                        <span>{row.label}</span>
                        <span>
                          {display(row.available_quantity)}
                        </span>
                      </div>
                    ))}
                  </section>
                )}
            </div>

            <p className="text-xs text-ink-secondary leading-relaxed">
              {report.note}
            </p>

            <p className="text-xs text-ink-secondary">
              Fictional sample snapshot: {report.snapshot_at}
            </p>
          </>
        )}
      </div>
    </div>
  )
}