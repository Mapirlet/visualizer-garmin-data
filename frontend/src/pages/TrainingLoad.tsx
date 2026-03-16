import { useQuery } from '@tanstack/react-query'
import { useFilters } from '../store/filters'
import { api } from '../lib/api'
import Chart from '../components/Chart'
import LoadingError from '../components/LoadingError'

const TYPE_COLORS = ['#2196F3', '#4CAF50', '#FF9800', '#E91E63', '#9C27B0', '#00BCD4']

export default function TrainingLoad() {
  const filters = useFilters()

  const { data, isLoading, error } = useQuery({
    queryKey: ['training-load', filters.start, filters.end, filters.types],
    queryFn: () => api.trainingLoad(filters),
    enabled: !!filters.start,
  })

  if (isLoading) return <LoadingError loading />
  if (error) return <LoadingError error={error as Error} />

  const bars = data?.bars ?? []
  const types = [...new Set(bars.map((b: any) => b.activity_type))]

  const traces = types.map((t: any, i) => ({
    type: 'bar' as const,
    name: t,
    x: bars.filter((b: any) => b.activity_type === t).map((b: any) => b.date),
    y: bars.filter((b: any) => b.activity_type === t).map((b: any) => b.training_load),
    marker: { color: TYPE_COLORS[i % TYPE_COLORS.length] },
  }))

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-white">Training Load Over Time</h2>
      {bars.length === 0 ? (
        <LoadingError empty emptyMsg="No training load data in selected range." />
      ) : (
        <Chart
          data={traces}
          layout={{
            barmode: 'stack',
            xaxis: { title: { text: 'Date' } },
            yaxis: { title: { text: 'Training Load' } },
          }}
          height={420}
        />
      )}
    </div>
  )
}
