import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@shared": path.resolve(rootDir, "../shared"),
      "lucide-react": path.resolve(rootDir, "node_modules/lucide-react"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/routes": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
