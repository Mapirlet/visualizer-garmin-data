// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
import Plot from 'react-plotly.js'
import type { Layout } from 'plotly.js'

interface Props {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any[]
  layout?: Partial<Layout>
  height?: number
  title?: string
}

const BASE_LAYOUT: Partial<Layout> = {
  paper_bgcolor: 'transparent',
  plot_bgcolor: '#1e2130',
  font: { color: '#e2e8f0', family: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', size: 12 },
  xaxis: { gridcolor: '#2d3148', linecolor: '#2d3148', zerolinecolor: '#2d3148' },
  yaxis: { gridcolor: '#2d3148', linecolor: '#2d3148', zerolinecolor: '#2d3148' },
  legend: { bgcolor: 'transparent', bordercolor: '#2d3148' },
  margin: { t: 40, b: 40, l: 50, r: 20 },
  modebar: { bgcolor: 'transparent', color: '#94a3b8', activecolor: '#e2e8f0' },
}

export default function Chart({ data, layout = {}, height = 350, title }: Props) {
  const merged: Partial<Layout> = {
    ...BASE_LAYOUT,
    ...layout,
    xaxis: { ...BASE_LAYOUT.xaxis, ...(layout.xaxis ?? {}) },
    yaxis: { ...BASE_LAYOUT.yaxis, ...(layout.yaxis ?? {}) },
    height,
    title: title ? { text: title, font: { size: 14, color: '#e2e8f0' } } : undefined,
  }

  return (
    <Plot
      data={data}
      layout={merged}
      config={{ responsive: true, displayModeBar: false }}
      style={{ width: '100%' }}
    />
  )
}
