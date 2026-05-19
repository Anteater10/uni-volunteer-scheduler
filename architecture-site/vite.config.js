import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Set to "/" for portfolio root, or "/architecture/" if hosted under a path.
  // Override at build time: `VITE_BASE=/architecture/ npm run build`.
  base: process.env.VITE_BASE || "/",
  server: {
    host: true,
    port: 5174,
  },
});
