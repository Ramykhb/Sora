import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const target = env.BACKEND_PROXY_TARGET || 'http://127.0.0.1:8000';
  return {
    plugins: [react()],
    base: './',
    server: {
      host: '127.0.0.1', port: 5173, strictPort: true,
      proxy: { '/api/v1': { target, ws: true }, '/health': { target }, '/ready': { target } },
    },
    preview: { host: '127.0.0.1', port: 5173, strictPort: true },
  };
});
