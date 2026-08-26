/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        body: ['DM Sans', 'sans-serif'],
      },
      keyframes: {
        'ping-once': {
          '0%':   { transform: 'scale(0.8)', opacity: '1' },
          '60%':  { transform: 'scale(1.2)', opacity: '0.8' },
          '100%': { transform: 'scale(1.0)', opacity: '0' },
        },
        'heart-burst': {
          '0%':   { transform: 'scale(1)' },
          '30%':  { transform: 'scale(1.5)' },
          '60%':  { transform: 'scale(0.9)' },
          '100%': { transform: 'scale(1)' },
        },
        'heart-shrink': {
          '0%':   { transform: 'scale(1)' },
          '40%':  { transform: 'scale(0.7)' },
          '100%': { transform: 'scale(1)' },
        },
        'drip': {
          '0%':   { transform: 'translateY(0) scale(1)', opacity: '1' },
          '40%':  { transform: 'translateY(4px) scale(0.95)', opacity: '0.9' },
          '70%':  { transform: 'translateY(-2px) scale(1.05)', opacity: '1' },
          '100%': { transform: 'translateY(0) scale(1)', opacity: '1' },
        },
        'fade-in-up': {
          '0%':   { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'shimmer': {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'fab-pulse': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(var(--accent-rgb, 247,147,26), 0.4)' },
          '50%':      { boxShadow: '0 0 0 10px rgba(var(--accent-rgb, 247,147,26), 0)' },
        },
        'confetti-fall': {
          '0%':   { transform: 'translateY(-20px) rotate(0deg)', opacity: '1' },
          '100%': { transform: 'translateY(100vh) rotate(720deg)', opacity: '0' },
        },
      },
      animation: {
        'ping-once':      'ping-once 0.5s ease-out forwards',
        'heart-burst':    'heart-burst 0.4s ease-out forwards',
        'heart-shrink':   'heart-shrink 0.3s ease-out forwards',
        'drip':           'drip 1.5s ease-in-out infinite',
        'fade-in-up':     'fade-in-up 0.4s ease-out forwards',
        'shimmer':        'shimmer 1.5s ease-in-out infinite',
        'fab-pulse':      'fab-pulse 2s ease-in-out infinite',
        'confetti-fall':  'confetti-fall linear forwards',
      },
      colors: {
        accent: {
          DEFAULT: 'var(--accent)',
          fg: 'var(--accent-fg)',
          text: 'var(--accent-text, var(--accent))',
        },
        theme: {
          page: 'var(--bg-page)',
          surface: 'var(--bg-surface)',
          surface2: 'var(--bg-surface-2)',
          border: 'var(--border)',
          primary: 'var(--text-primary)',
          muted: 'var(--text-muted)',
          subtle: 'var(--text-subtle)',
        },
      },
    },
  },
  plugins: [],
}
