import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: {
          primary: "#F8F8F8",
          secondary: "rgba(255,255,255,0.55)",
          tertiary: "rgba(255,255,255,0.30)",
        },
        accent: {
          DEFAULT: "#00E5FF",
          glow: "rgba(0,229,255,0.45)",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
        display: ["var(--font-neue)", "Neue Montreal", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "JetBrains Mono", "monospace"],
        serif: ["var(--font-instrument-serif)", "Georgia", "serif"],
      },
      animation: {
        "pulse-soft": "pulse-soft 2.4s cubic-bezier(0.65, 0, 0.35, 1) infinite",
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.25, 1, 0.5, 1) infinite",
      },
      keyframes: {
        "pulse-soft": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.6", transform: "scale(0.92)" },
        },
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 rgba(0, 229, 255, 0.5)" },
          "70%": { boxShadow: "0 0 0 8px rgba(0, 229, 255, 0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(0, 229, 255, 0)" },
        },
      },
      borderWidth: {
        DEFAULT: "1px",
        hairline: "0.5px",
        "3": "3px",
        "5": "5px",
        "6": "6px",
      },
      transitionTimingFunction: {
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
        "out-quart": "cubic-bezier(0.25, 1, 0.5, 1)",
        "in-out-smooth": "cubic-bezier(0.65, 0, 0.35, 1)",
      },
    },
  },
  plugins: [],
};
export default config;
