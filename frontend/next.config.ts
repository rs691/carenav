import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // WSL / Docker Desktop bridge often hits the Next HMR endpoint from this host
  allowedDevOrigins: ["172.22.240.1", "localhost", "127.0.0.1"],
};

export default nextConfig;
