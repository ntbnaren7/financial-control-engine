/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', '"Liberation Mono"', '"Courier New"', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        fce: {
          bg: '#0f172a', // slate-900
          surface: '#1e293b', // slate-800
          surfaceHover: '#334155', // slate-700
          text: '#f1f5f9', // slate-100
          textMuted: '#94a3b8', // slate-400
          accent: '#38bdf8', // sky-400
          success: '#10b981', // emerald-500
          warning: '#f59e0b', // amber-500
          danger: '#ef4444', // red-500
        }
      }
    },
  },
  plugins: [],
}
