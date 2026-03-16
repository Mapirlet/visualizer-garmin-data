import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        garmin: {
          blue: '#1a73e8',
          dark: '#1a1d23',
          sidebar: '#0f1117',
          surface: '#1e2130',
          border: '#2d3148',
          text: '#e2e8f0',
          muted: '#94a3b8',
        },
      },
    },
  },
  plugins: [],
} satisfies Config
