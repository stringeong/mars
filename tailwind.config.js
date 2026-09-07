/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f1f2fe',
          100: '#e5e7fd',
          200: '#cdd1fb',
          300: '#aab0f8',
          400: '#8087f2',
          500: '#6366f1',
          600: '#4c46e0',
          700: '#3f38c4',
          800: '#35309e',
          900: '#302d7d',
        },
        surface: {
          DEFAULT: '#f6f8ff',
          card: '#ffffff',
          sunk: '#eef1fb',
        },
        ink: {
          900: '#0f1226',
          700: '#3a3d5c',
          500: '#6b6f94',
          300: '#a3a7c9',
        },
      },
      fontFamily: {
        sans: ['"Pretendard Variable"', 'Pretendard', '-apple-system', 'sans-serif'],
      },
      boxShadow: {
        soft: '0 1px 2px rgba(15, 18, 38, 0.04), 0 8px 24px rgba(15, 18, 38, 0.06)',
      },
      borderRadius: {
        xl2: '1.25rem',
      },
    },
  },
  plugins: [],
}
