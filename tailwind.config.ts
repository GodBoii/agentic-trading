import type { Config } from "tailwindcss";

/**
 * Colour policy
 * -------------
 * Every colour here resolves to a custom property declared in
 * `app/globals.css`, and nothing here declares a literal. That is what makes
 * the light theme possible: `[data-theme="light"]` redefines the properties,
 * and every Tailwind utility in the app follows without being touched.
 *
 * Two kinds of token appear below, and the difference matters at call sites.
 *
 * Tonal colours are declared as `R G B` channel triplets (`--accent-rgb`) and
 * wired through `rgb(... / <alpha-value>)`, so Tailwind's opacity modifiers
 * work off the same source of truth: `border-danger/30` and
 * `var(--dash-negative)` can never drift apart.
 *
 * Surface colours (`canvas`, `panel`, `surface`, `solid`) are pre-composed
 * values and therefore take no opacity modifier. They are already the right
 * colour for the current theme; layering opacity on top of them is what
 * produced the muddy stacked washes this replaced.
 *
 * `success`/`danger` are the semantic aliases used for run and order state.
 * `positive`/`negative` are the financial aliases used for P&L direction. They
 * intentionally share a value: a losing position and a failed run should read
 * as the same red.
 */
const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  /**
   * The theme is carried on `data-theme` rather than a class. A `dark` class
   * cannot express the third state the app actually has — follow the system —
   * and an attribute lets the pre-hydration script set light, dark or the
   * resolved system value with one write.
   */
  darkMode: ["variant", '[data-theme="dark"] &'],
  theme: {
    extend: {
      colors: {
        // Text scale.
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
        // The surface a floating layer paints on.
        pop: "var(--dash-pop)",
        line: {
          DEFAULT: "var(--dash-border)",
          strong: "var(--dash-border-strong)",
        },
        /**
         * Translucent fills, quietest first. These replace the
         * `bg-white/[0.03]` idiom that was spread across three dozen call
         * sites and was invisible the moment a light theme existed.
         */
        surface: {
          DEFAULT: "var(--fill-subtle)",
          soft: "var(--fill-soft)",
          strong: "var(--fill-strong)",
          hover: "var(--fill-hover)",
          track: "var(--fill-track)",
        },
        /** The one committing action per screen; inverted against the canvas. */
        solid: {
          DEFAULT: "var(--solid-bg)",
          hover: "var(--solid-bg-hover)",
          fg: "var(--solid-fg)",
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
        sans: ["var(--font-body)", "Manrope", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-headline)", "Outfit", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-numeric)", "IBM Plex Mono", "ui-monospace", "monospace"],
        serif: ["var(--font-editorial)", "Instrument Serif", "Georgia", "serif"],
      },
      boxShadow: {
        panel: "var(--shadow-panel)",
        pop: "var(--shadow-pop)",
        solid: "var(--shadow-solid)",
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
        // Tinted from the accent channel, so the ring follows the theme
        // instead of pulsing the old hardcoded cyan.
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 rgb(var(--accent-rgb) / 0.45)" },
          "70%": { boxShadow: "0 0 0 8px rgb(var(--accent-rgb) / 0)" },
          "100%": { boxShadow: "0 0 0 0 rgb(var(--accent-rgb) / 0)" },
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
        // The house curve. Referenced as `ease-smooth` instead of the
        // arbitrary-value form that was repeated at ~40 call sites.
        smooth: "cubic-bezier(0.22, 1, 0.36, 1)",
        bouncy: "cubic-bezier(0.34, 3.85, 0.64, 1)",
      },
      transitionDuration: {
        quick: "150ms",
        fast: "250ms",
        medium: "350ms",
        slow: "400ms",
      },
    },
  },
  plugins: [],
};
export default config;
