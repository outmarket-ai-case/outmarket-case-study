import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Local dev only. In every built image nginx owns the /api proxy, so the
    // app never needs a build-time backend URL -- one artifact, any cloud.
    proxy: {
      "/api": { target: process.env.BACKEND_URL ?? "http://localhost:8000", changeOrigin: true },
      "/healthz": { target: process.env.BACKEND_URL ?? "http://localhost:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
