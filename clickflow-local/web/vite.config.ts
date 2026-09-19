import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Configuración mínima: SPA de React servida por Vite en desarrollo y como
// build estático en producción (ver docs/DEPLOY.md). El backend expone su
// API en otro puerto/host, así que las llamadas usan una URL base
// configurable por variable de entorno (VITE_API_BASE_URL).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API_PROXY || "http://localhost:8787",
        changeOrigin: true,
      },
    },
  },
});
