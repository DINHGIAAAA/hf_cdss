import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(rootDir, "src"),
      "@shared": path.resolve(rootDir, "../shared"),
      "lucide-react": path.resolve(rootDir, "node_modules/lucide-react"),
    },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    watch: {
      // Required for reliable HMR with Docker Desktop bind mounts on Windows.
      usePolling: true,
      interval: 300,
    },
    proxy: {
      // Same-origin browser calls → cookie is scoped to :5173 and forwarded to backend.
      "/api": {
        target: process.env.VITE_DEV_PROXY_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        cookieDomainRewrite: "",
      },
      "/routes": {
        target: process.env.VITE_DEV_PROXY_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        cookieDomainRewrite: "",
      },
    },
  },
});
