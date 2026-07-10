import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        pitch: "#0f1923",
        surface: "#1a2535",
        border: "#243044",
        epl: "#3d0aff",
        wc: "#c9a227",
      },
    },
  },
  plugins: [],
};

export default config;
