import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
        port: "8000",
        pathname: "/api/**",
      },
      {
        protocol: "http",
        hostname: "127.0.0.1",
        port: "9000",
        pathname: "/cctv-analysis/**",
      },
      {
        protocol: "http",
        hostname: "localhost",
        port: "9000",
        pathname: "/cctv-analysis/**",
      },
      // Allow backend URL from env
      ...(process.env.AI_BACKEND_URL
        ? [
            {
              protocol: new URL(process.env.AI_BACKEND_URL).protocol.replace(
                ":",
                ""
              ) as "http" | "https",
              hostname: new URL(process.env.AI_BACKEND_URL).hostname,
            },
          ]
        : []),
      // Development: picsum for mock thumbnails
      { protocol: "https", hostname: "picsum.photos" },
    ],
  },
  experimental: {
    // Enable server actions for future use
    serverActions: {
      allowedOrigins: ["localhost:3000"],
    },
  },
};

export default nextConfig;
