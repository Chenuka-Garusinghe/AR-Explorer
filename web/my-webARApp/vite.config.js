import { defineConfig } from "vite";

export default defineConfig({
  server: {
    allowedHosts: [
      "0ccd4c7fa124.ngrok-free.app",
      "f488b18d8cad.ngrok-free.app",
      "6ce96c8a350e.ngrok-free.app",
      "c8e7801e2f95.ngrok-free.app",
    ],
  },
  plugins: [
    {
      name: "client-log",
      configureServer(server) {
        server.middlewares.use("/__log", (req, res) => {
          let body = "";
          req.on("data", (chunk) => {
            body += chunk;
          });
          req.on("end", () => {
            if (body) {
              console.log("[client]", body);
            }
            res.statusCode = 204;
            res.end();
          });
        });
      },
    },
  ],
});
