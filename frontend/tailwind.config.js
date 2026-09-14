/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
        sans: ['"Inter"', 'system-ui', 'sans-serif'],
      },
      colors: {
        fce: {
          bg: '#010A1C',
          bgAlt: '#02112C',
          surface: 'rgba(255, 255, 255, 0.03)',
          surfaceHover: 'rgba(255, 255, 255, 0.06)',
          border: 'rgba(255, 255, 255, 0.1)',
          text: '#FFFFFF', 
          textMuted: '#94A3B8',
          accent: '#3B82F6',
          accentHover: '#2563EB',
          accentGlow: '#1D4ED8',
          success: '#10B981', 
          warning: '#F59E0B', 
          danger: '#EF4444', 
        }
      },
      backgroundImage: {
        'grid-pattern': "url(\"data:image/svg+xml,%3Csvg width='40' height='40' viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M0 0h40v40H0V0zm1 1h38v38H1V1z' fill='%23ffffff' fill-opacity='0.03' fill-rule='evenodd'/%3E%3C/svg%3E\")",
        'radial-glow': 'radial-gradient(circle at 50% 50%, rgba(59, 130, 246, 0.15) 0%, rgba(1, 10, 28, 0) 50%)',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-15px)' },
        },
        dash: {
          'to': { strokeDashoffset: '-100' },
        }
      }
    },
  },
  plugins: [],
}
