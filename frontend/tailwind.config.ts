import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./hooks/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      animation: {
        "wave-1": "wave 0.6s ease-in-out infinite alternate",
        "wave-2": "wave 0.6s ease-in-out 0.1s infinite alternate",
        "wave-3": "wave 0.6s ease-in-out 0.2s infinite alternate",
        "wave-4": "wave 0.6s ease-in-out 0.3s infinite alternate",
        "wave-5": "wave 0.6s ease-in-out 0.4s infinite alternate",
        "wave-6": "wave 0.6s ease-in-out 0.2s infinite alternate",
        "wave-7": "wave 0.6s ease-in-out 0.1s infinite alternate",
        "pulse-ring": "pulse-ring 2s ease-out infinite",
        "pulse-ring-slow": "pulse-ring 2.8s ease-out 0.5s infinite",
        "fade-in": "fade-in 0.3s ease-out",
        "slide-up": "slide-up 0.4s ease-out",
      },
      keyframes: {
        wave: {
          "0%": { transform: "scaleY(0.15)" },
          "100%": { transform: "scaleY(1)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(1)", opacity: "0.6" },
          "100%": { transform: "scale(1.5)", opacity: "0" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-up": {
          "0%": { transform: "translateY(8px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
      colors: {
        brand: {
          green: "#10b981",
          "green-dark": "#059669",
          "green-glow": "rgba(16,185,129,0.3)",
          bg: "#050505",
          card: "#0f0f0f",
          border: "#1f1f1f",
          "border-active": "#374151",
        },
      },
    },
  },
  plugins: [],
};

export default config;
