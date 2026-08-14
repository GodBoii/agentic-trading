import type { Config } from "tailwindcss";

/**
 * Colour policy
 * -------------
 * Every tonal colour resolves to a channel triplet declared once in
 * `app/globals.css` (`--*-rgb`). Declaring them here with `<alpha-value>`
 * means Tailwind's opacity modifiers work off the same source of truth,
 * so `border-danger/30` and `var(--dash-negative)` can never drift apart.
 *
 * `success`/`danger` are the semantic aliases used for run and order state.
 * `positive`/`negative` are the financial aliases used for P&L direction.
 * They intentionally share a value: a losing position and a failed run
 * should read as the same red.
 */
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
        // Text scale — shared by the marketing surface and the product shell.
        ink: {
          primary: "var(--dash-text)",
          secondary: "var(--dash-text-secondary)",
          tertiary: "var(--dash-text-muted)",
        },
        // Structure.
        canvas: "var(--dash-canvas)",
        panel: {
          DEFAULT: "var(--dash-panel)",
          inset: "var(--dash-panel-inset)",
        },
        line: {
          DEFAULT: "var(--dash-border)",
          strong: "var(--dash-border-strong)",
        },
        // Tone.
        accent: {
          DEFAULT: "rgb(var(--accent-rgb) / <alpha-value>)",
          glow: "rgb(var(--accent-rgb) / 0.45)",
        },
        success: "rgb(var(--dash-positive-rgb) / <alpha-value>)",
        danger: "rgb(var(--dash-negative-rgb) / <alpha-value>)",
        warning: "rgb(var(--dash-warning-rgb) / <alpha-value>)",
        positive: "rgb(var(--dash-positive-rgb) / <alpha-value>)",
        negative: "rgb(var(--dash-negative-rgb) / <alpha-value>)",
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
