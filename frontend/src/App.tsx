import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import Layout from './components/Layout'
import { useFilters } from './store/filters'
import { api } from './lib/api'

import HRAnalysis from './pages/HRAnalysis'
import TrainingLoad from './pages/TrainingLoad'
import SleepTrends from './pages/SleepTrends'
import Technique from './pages/Technique'
import Routes_ from './pages/Routes'
import Progress from './pages/Progress'
import ActivityDetail from './pages/ActivityDetail'
import Summary from './pages/Summary'

function AppRoutes() {
  const { setStart, setEnd, setTypes } = useFilters()

  // Bootstrap date range and default types on first load
  const { data: rangeData } = useQuery({
    queryKey: ['date-range'],
    queryFn: api.dateRange,
  })
  const { data: typesData } = useQuery({
    queryKey: ['activity-types'],
    queryFn: api.activityTypes,
  })

  useEffect(() => {
    if (rangeData) {
      setStart(rangeData.min)
      setEnd(rangeData.max)
    }
  }, [rangeData, setStart, setEnd])

  useEffect(() => {
    if (typesData) {
      const running = (typesData.types as string[]).filter(
        (t) => t.includes('running') && !t.includes('treadmill'),
      )
      setTypes(running.length > 0 ? running : typesData.types)
    }
  }, [typesData, setTypes])

  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/activity" replace />} />
        <Route path="hr-analysis" element={<HRAnalysis />} />
        {/* keep old URLs working */}
        <Route path="hr-pace" element={<Navigate to="/hr-analysis" replace />} />
        <Route path="hr-sleep" element={<Navigate to="/hr-analysis" replace />} />
        <Route path="training-load" element={<TrainingLoad />} />
        <Route path="sleep" element={<SleepTrends />} />
        <Route path="technique" element={<Technique />} />
        <Route path="routes" element={<Routes_ />} />
        <Route path="progress" element={<Progress />} />
        <Route path="activity/:id?" element={<ActivityDetail />} />
        <Route path="summary" element={<Summary />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
