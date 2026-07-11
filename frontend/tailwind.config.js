/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        atlas: {
          bg:      '#121212',
          surface: '#181818',
          elevated:'#242424',
          border:  '#2a2a2a',
          muted:   '#a7a7a7',
          text:    '#e7e7e7',
          heading: '#ffffff',
          amber:   '#f9c74f',
          indigo:  '#62a8ff',
          sage:    '#7AB89A',
          rose:    '#ff5c8a',
          lime:    '#1ED760',
        }
      },
      fontFamily: {
        display: ['"Archivo Narrow"', 'sans-serif'],
        mono:    ['"JetBrains Mono"', 'monospace'],
        body:    ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
