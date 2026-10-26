import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";

const API = "http://localhost:8000";

// With the API down, Vite's proxy answers 500, which the console would read as the API failing. 502 is what a
// gateway says when it cannot reach the server behind it, so the console says the API isn't answering instead.
const toApi = (target = API): ProxyOptions => ({
  target,
  configure: (proxy) => {
    proxy.on("error", (_err, _req, res) => {
      if ("writeHead" in res && !res.headersSent) res.writeHead(502, { "content-type": "text/plain" }).end("API unreachable");
    });
  },
});

const PATHS = ["/proposals", "/matches", "/state", "/decisions", "/packages", "/metrics", "/viewer-groups", "/schedule",
  "/recap", "/deliveries", "/healthz"];

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/ws": { target: "ws://localhost:8000", ws: true },
      ...Object.fromEntries(PATHS.map((p) => [p, toApi()])),
    },
  },
});
