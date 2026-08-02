/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#F8FAFC',
        surface: '#FFFFFF',
        border: '#E2E8F0',
        primary: '#2563EB',
        'primary-dark': '#1D4ED8',
        secondary: '#3B82F6',
        accent: '#60A5FA',
        ink: '#0F172A',
        'ink-secondary': '#64748B',
        success: '#22C55E',
        warning: '#F59E0B',
        danger: '#EF4444',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 0 0 1px rgba(37, 99, 235, 0.07), 0 2px 10px -2px rgba(37, 99, 235, 0.14)',
        'card-hover': '0 0 0 1px rgba(37, 99, 235, 0.16), 0 6px 18px -4px rgba(37, 99, 235, 0.30)',
        'nav-glow': '0 0 0 1px rgba(37, 99, 235, 0.12), 0 2px 10px -2px rgba(37, 99, 235, 0.22)',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.18s ease-out',
        shimmer: 'shimmer 4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
