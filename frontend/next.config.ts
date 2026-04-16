import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow the @vapi-ai/web package (uses browser APIs) to be bundled normally
  transpilePackages: ["@vapi-ai/web"],
};

export default nextConfig;
