import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next.js 16 blocks cross-origin HMR by default. The dev server binds to
  // both `localhost` and `127.0.0.1`, but Next treats `127.0.0.1` as a
  // foreign origin and refuses to serve HMR chunks to it — which silently
  // breaks hydration (the client never finishes loading, useEffect never
  // fires, the picker stays empty). Allow both so either spelling works.
  allowedDevOrigins: ["localhost", "127.0.0.1"],
};

export default nextConfig;
