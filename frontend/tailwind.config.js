/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        cura: {
          50: "#eef7f4",
          100: "#d5ede4",
          200: "#afdccc",
          300: "#7bc4ac",
          400: "#4ba78a",
          500: "#328c70",
          600: "#25705a",
          700: "#205a49",
          800: "#1d493c",
          900: "#1a3d33",
          950: "#0d221c",
        },
      },
      fontFamily: {
        sans: ['"DM Sans"', "system-ui", "sans-serif"],
        display: ['"Fraunces"', "serif"],
      },
    },
  },
  plugins: [],
};
