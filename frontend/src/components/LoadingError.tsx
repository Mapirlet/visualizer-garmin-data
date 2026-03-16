interface Props {
  loading?: boolean
  error?: Error | null
  empty?: boolean
  emptyMsg?: string
  cacheMsg?: string
}

export default function LoadingError({ loading, error, empty, emptyMsg, cacheMsg }: Props) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-garmin-muted">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-garmin-blue mr-3" />
        Loading…
      </div>
    )
  }
  if (error) {
    return (
      <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
        Error: {error.message}
      </div>
    )
  }
  if (cacheMsg) {
    return (
      <div className="bg-yellow-900/30 border border-yellow-700 rounded-lg p-4 text-yellow-300">
        <p className="font-medium">Cache not built yet</p>
        <pre className="mt-2 text-sm bg-black/30 rounded p-2">{cacheMsg}</pre>
      </div>
    )
  }
  if (empty) {
    return (
      <div className="flex items-center justify-center h-48 text-garmin-muted">
        {emptyMsg || 'No data in selected range.'}
      </div>
    )
  }
  return null
}
