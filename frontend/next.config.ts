import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow the Next.js dev server to proxy API requests to FastAPI
  async rewrites() {
    return process.env.NODE_ENV === "development"
      ? [
          {
            source: "/api/:path*",
            destination: "http://localhost:8000/api/:path*",
          },
        ]
      : [];
  },
};

export default nextConfig;
