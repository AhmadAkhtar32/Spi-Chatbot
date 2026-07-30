/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#F4F6F8',
        surface: '#FFFFFF',
        border: '#D1D5DB',
        primary: '#2563EB',
        'primary-dark': '#1D4ED8',
        ink: '#111827',
        'ink-secondary': '#6B7280',
        success: '#16A34A',
        warning: '#F59E0B',
        error: '#DC2626',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      spacing: {
        // 8px baseline system — most values already fall on this grid
        // via Tailwind's default scale (2=8px*0.5 etc.); these fill gaps.
        18: '4.5rem',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.18s ease-out',
      },
    },
  },
  plugins: [],
}
