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
        // Sentinel palette
        canvas: {
          DEFAULT: "#030303",
          raised: "#080808",
          card: "#0A0A0C",
        },
        ink: {
          primary: "#F8F8F8",
          secondary: "rgba(255,255,255,0.55)",
          tertiary: "rgba(255,255,255,0.30)",
        },
        accent: {
          DEFAULT: "#00E5FF",
          glow: "rgba(0,229,255,0.45)",
        },
        profit: "#00FF9D",
        loss: "#FF5B5B",
        hairline: "rgba(255,255,255,0.07)",
        hairlineStrong: "rgba(255,255,255,0.14)",

        // Legacy brutalist tokens — preserved for /login, /signup, /dashboard
        // and the existing brutal-* utility classes below.
        brutal: {
          black: "#000000",
          white: "#FFFFFF",
          cream: "#FFFEF2",
          green: "#00FF00",
          red: "#FF0000",
          yellow: "#FFFF00",
          gray: {
            900: "#0A0A0A",
            800: "#1A1A1A",
            700: "#2A2A2A",
          },
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
        display: ["var(--font-neue)", "Neue Montreal", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "JetBrains Mono", "monospace"],
        serif: ["var(--font-instrument-serif)", "Georgia", "serif"],
      },
      letterSpacing: {
        tightest: "-0.05em",
        ultra: "-0.04em",
        sentinel: "-0.06em",
      },
      fontSize: {
        // Sentinel display scale
        "sentinel-hero": ["clamp(3.25rem, 11vw, 13rem)", { lineHeight: "0.85", letterSpacing: "-0.06em" }],
        "display-xl": ["clamp(3.5rem, 8.5vw, 10.5rem)", { lineHeight: "0.92", letterSpacing: "-0.045em" }],
        "display-lg": ["clamp(2.75rem, 6vw, 7rem)", { lineHeight: "0.95", letterSpacing: "-0.04em" }],
        "display-md": ["clamp(2rem, 4vw, 4.5rem)", { lineHeight: "1", letterSpacing: "-0.035em" }],
        "display-sm": ["clamp(1.5rem, 2.4vw, 2.5rem)", { lineHeight: "1.05", letterSpacing: "-0.03em" }],
        "eyebrow": ["0.6875rem", { lineHeight: "1", letterSpacing: "0.2em" }],
      },
      animation: {
        "pulse-soft": "pulse-soft 2.4s cubic-bezier(0.65, 0, 0.35, 1) infinite",
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.25, 1, 0.5, 1) infinite",
        "drift": "drift 24s cubic-bezier(0.65, 0, 0.35, 1) infinite",
        "drift-slow": "drift-slow 30s cubic-bezier(0.65, 0, 0.35, 1) infinite",
        "scan-line": "scan-line 6s linear infinite",
        "marquee": "marquee 60s linear infinite",
        "spin-slow": "spin 30s linear infinite",
        "spin-slower": "spin 60s linear infinite",
        "spin-reverse-slow": "spin-reverse 45s linear infinite",
        "ticker-blink": "blink 1.4s ease-in-out infinite",
        "slide-in-right": "slide-in-right 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)",
        "slide-in-left": "slide-in-left 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)",
        "pop": "pop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)",
        "shake": "shake 0.5s cubic-bezier(.36,.07,.19,.97)",
        // Sentinel-specific
        "core-rotate": "core-rotate 80s linear infinite",
        "core-rotate-rev": "core-rotate-rev 110s linear infinite",
        "core-pulse": "core-pulse 4s ease-in-out infinite",
        "flow": "flow 3.2s linear infinite",
        "flow-slow": "flow 6s linear infinite",
        "blink": "blink 1.2s ease-in-out infinite",
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
        drift: {
          "0%, 100%": { transform: "translate(0, 0)" },
          "33%": { transform: "translate(30px, -20px)" },
          "66%": { transform: "translate(-20px, 20px)" },
        },
        "drift-slow": {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "50%": { transform: "translate(-20px, 30px) scale(1.05)" },
        },
        "scan-line": {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(2000%)" },
        },
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
        "spin-reverse": {
          "0%": { transform: "rotate(360deg)" },
          "100%": { transform: "rotate(0deg)" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.3" },
        },
        "slide-in-right": {
          from: { transform: "translateX(100%)", opacity: "0" },
          to: { transform: "translateX(0)", opacity: "1" },
        },
        "slide-in-left": {
          from: { transform: "translateX(-100%)", opacity: "0" },
          to: { transform: "translateX(0)", opacity: "1" },
        },
        pop: {
          "0%": { transform: "scale(0.8)", opacity: "0" },
          "50%": { transform: "scale(1.05)" },
          "100%": { transform: "scale(1)", opacity: "1" },
        },
        shake: {
          "0%, 100%": { transform: "translateX(0)" },
          "10%, 30%, 50%, 70%, 90%": { transform: "translateX(-4px)" },
          "20%, 40%, 60%, 80%": { transform: "translateX(4px)" },
        },
        "core-rotate": {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
        "core-rotate-rev": {
          "0%": { transform: "rotate(360deg)" },
          "100%": { transform: "rotate(0deg)" },
        },
        "core-pulse": {
          "0%, 100%": { opacity: "0.55", transform: "scale(1)" },
          "50%": { opacity: "0.85", transform: "scale(1.04)" },
        },
        flow: {
          "0%": { strokeDashoffset: "0" },
          "100%": { strokeDashoffset: "-200" },
        },
      },
      borderWidth: {
        DEFAULT: "1px",
        hairline: "0.5px",
        "3": "3px",
        "5": "5px",
        "6": "6px",
      },
      boxShadow: {
        "brutal": "8px 8px 0px #FFFFFF",
        "brutal-sm": "4px 4px 0px #FFFFFF",
        "brutal-lg": "12px 12px 0px #FFFFFF",
        "brutal-green": "8px 8px 0px #00FF00",
        "brutal-red": "8px 8px 0px #FF0000",
        "sentinel-glow": "0 0 60px rgba(0,229,255,0.20), 0 0 120px rgba(0,229,255,0.08)",
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
