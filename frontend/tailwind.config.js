/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#142033",
        navy: "#1b3048",
        gold: "#9a7436",
        sand: "#f3efe7",
        paper: "#fbf9f5",
        line: "#e5ddd1",
        mist: "#6d7580",
      },
      fontFamily: {
        serif: ["Newsreader", "Georgia", "serif"],
        sans: ["Outfit", "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        card: "0 16px 40px rgba(20, 32, 51, 0.06)",
      },
    },
  },
  plugins: [],
};
