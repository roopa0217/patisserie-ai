/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Near-black warm background
        obsidian: '#0f0d0b',
        // Dark brown surfaces
        bark: '#1a1410',
        bark2: '#231c16',
        bark3: '#2e231a',
        // Copper accent
        copper: '#c07840',
        'copper-light': '#d4935a',
        'copper-dark': '#a05e28',
        // Gold accent
        gold: '#c8a84b',
        'gold-light': '#dfc06a',
        // Cream text
        cream: '#f0e8d8',
        'cream-muted': '#b89c7a',
        // Status colours
        'pass-green': '#4a7c59',
        'fail-red': '#8b3a3a',
      },
      fontFamily: {
        serif: ['Playfair Display', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-in',
        'slide-up': 'slideUp 0.25s ease-out',
        'pulse-dot': 'pulseDot 1.4s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseDot: {
          '0%, 80%, 100%': { transform: 'scale(0.6)', opacity: '0.4' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
