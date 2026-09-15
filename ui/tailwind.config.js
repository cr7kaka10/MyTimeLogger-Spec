/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: '#2563EB',
        ink: '#1a1a1a',
      },
    },
  },
  plugins: [],
}
