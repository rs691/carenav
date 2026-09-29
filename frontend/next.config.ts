import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // WSL / Docker Desktop bridge often hits the Next HMR endpoint from this host
  allowedDevOrigins: ["172.22.240.1", "localhost", "127.0.0.1"],
  // Pin Turbopack to frontend/ (avoids picking up a parent-repo lockfile)
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
