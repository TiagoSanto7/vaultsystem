import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Em desenvolvimento (`npm run dev`), as chamadas a /v1 vão para a API local.
// Em produção, a própria API serve estes arquivos (api/app/main.py).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/v1": process.env.VAULT_API ?? "http://127.0.0.1:8670" } },
  build: { outDir: "dist", sourcemap: false },
});
