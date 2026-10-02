/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'rgb(var(--color-bg) / <alpha-value>)',
        surface: 'rgb(var(--color-surface) / <alpha-value>)',
        border: 'rgb(var(--color-border) / <alpha-value>)',
        primary: 'rgb(var(--color-primary) / <alpha-value>)',
        'primary-dark': 'rgb(var(--color-primary-dark) / <alpha-value>)',
        secondary: 'rgb(var(--color-secondary) / <alpha-value>)',
        accent: 'rgb(var(--color-accent) / <alpha-value>)',
        ink: 'rgb(var(--color-ink) / <alpha-value>)',
        'ink-secondary': 'rgb(var(--color-ink-secondary) / <alpha-value>)',
        success: 'rgb(var(--color-success) / <alpha-value>)',
        warning: 'rgb(var(--color-warning) / <alpha-value>)',
        danger: 'rgb(var(--color-danger) / <alpha-value>)',
        // Two extra tokens that replace hardcoded Tailwind grays
        // (bg-slate-50 / bg-slate-100) used for hover washes and
        // static muted panels — those didn't adapt to dark mode.
        muted: 'rgb(var(--color-muted) / <alpha-value>)',
        hover: 'rgb(var(--color-hover) / <alpha-value>)',
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