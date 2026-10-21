import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The UI talks to the FastAPI backend on :8000 through this proxy (REST + WebSocket).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
