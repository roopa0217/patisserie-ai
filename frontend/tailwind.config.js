/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Premium pastry palette — warm cream base + deep bordeaux/wine accent
        parchment: '#FDF8F2',   // main background
        sand: '#F5EDE0',        // sidebar
        linen: '#EDE1CC',       // card/table headers
        stone: '#DDD0B8',       // borders
        'stone-dark': '#C4B095',// stronger borders
        // Text
        ink: '#1A0A08',
        'ink-muted': '#5C3A28',
        'ink-faint': '#9C7860',
        // Vivid crimson — primary accent (vibrant, premium)
        copper: '#B01830',
        'copper-light': '#C82038',
        'copper-dark': '#8C1226',
        // Gold — secondary accent
        gold: '#B8882A',
        'gold-light': '#D4A43C',
        // Status
        'pass-green': '#1A5C35',
        'fail-red': '#8B1A1A',
      },
      fontFamily: {
        serif: ['Playfair Display', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'fade-in':    'fadeIn 0.25s ease-out',
        'slide-up':   'slideUp 0.28s ease-out',
        'pulse-dot':  'pulseDot 1.4s ease-in-out infinite',
        'splash-in':  'splashIn 0.6s cubic-bezier(0.16,1,0.3,1) both',
        'line-grow':  'lineGrow 0.5s ease-out 0.35s both',
        'fade-up':    'fadeUp 0.55s ease-out both',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%':   { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseDot: {
          '0%, 80%, 100%': { transform: 'scale(0.6)', opacity: '0.4' },
          '40%':           { transform: 'scale(1)',   opacity: '1' },
        },
        splashIn: {
          '0%':   { opacity: '0', transform: 'scale(0.7) translateY(12px)' },
          '100%': { opacity: '1', transform: 'scale(1) translateY(0)' },
        },
        lineGrow: {
          '0%':   { transform: 'scaleX(0)', opacity: '0' },
          '100%': { transform: 'scaleX(1)', opacity: '1' },
        },
        fadeUp: {
          '0%':   { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
