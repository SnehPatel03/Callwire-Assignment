import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// In dev, /v1 and /stream are proxied to the engine so the browser never hits CORS.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const target = env.VITE_API_TARGET || "http://localhost:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        "/v1": { target, changeOrigin: true },
        "/stream": { target, ws: true, changeOrigin: true },
      },
    },
  };
});
