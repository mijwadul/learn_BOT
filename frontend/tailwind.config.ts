import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#161b22",
        foreground: "#c9d1d9",
        brand: {
          green: "#2ea043",
          red: "#da3633",
          blue: "#58a6ff",
          dark: "#0d1117",
          panel: "#21262d"
        }
      },
    },
  },
  plugins: [],
};
export default config;
