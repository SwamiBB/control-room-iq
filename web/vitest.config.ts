import { defineConfig } from "vitest/config";
// Pure-function tests in node: no DOM. api.ts reads `location` unless VITE_API_URL is set.
export default defineConfig({ test: { environment: "node", env: { VITE_API_URL: "http://localhost:8000" } } });
