import type { NextConfig } from "next";

const isStaticExport = process.env.NEXT_OUTPUT === "export";

const nextConfig: NextConfig = {
  // Allow ngrok and similar tunnel origins in dev
  allowedDevOrigins: ["*.ngrok-free.dev", "*.ngrok.io"],
  // Pin Turbopack root to this directory so it doesn't pick up unrelated lockfiles
  turbopack: {
    root: __dirname,
  },
  // Static export for Firebase Hosting (set NEXT_OUTPUT=export in CI)
  ...(isStaticExport
    ? { output: "export" }
    : {
        // Dev-only: proxy /api to backend. In production, firebase.json handles routing.
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
            },
          ];
        },
      }),
};

export default nextConfig;
