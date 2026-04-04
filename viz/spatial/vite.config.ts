import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  root: ".",
  publicDir: "public",
  define: {
    __PROJECT_ROOT__: JSON.stringify(resolve(__dirname, "../..")),
  },
  server: {
    port: 5174,
    proxy: {
      // Proxy API calls to the existing AGORA viz server when running
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
        // Don't fail if the viz server isn't running — the viewer has a
        // direct-file fallback mode that loads from /runs/ instead.
        configure: (proxy) => {
          proxy.on("error", () => {});
        },
      },
    },
    // Serve the project-root runs/ directory so the viewer can load data
    // directly without the viz server running.
    fs: {
      allow: [
        ".",
        resolve(__dirname, "../../runs"),
        resolve(__dirname, "../../scenarios"),
      ],
    },
  },
  build: {
    outDir: "dist",
  },
});
