/** @type {import('next').NextConfig} */
// Phase 15: production security headers. Applied to every response from
// Next.js (pages, static assets, API routes). CSP does not include inline
// script allowances beyond what Next.js hydration requires in dev.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
];

const nextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "lh3.googleusercontent.com" },
    ],
  },
  experimental: {
    optimizePackageImports: ["framer-motion", "lucide-react", "@supabase/supabase-js"],
  },
  webpack: (config, { dev }) => {
    if (dev) {
      config.watchOptions = {
        ...(config.watchOptions ?? {}),
        ignored: [
          "**/.git/**",
          "**/.next/**",
          "**/node_modules/**",
          "**/backend/**",
          "**/__pycache__/**",
          "**/.pytest_cache/**",
          "**/coverage/**",
          "**/.stitch/**",
          "**/dist/**",
          "**/scripts/**",
          // Stray writes to any of these during `next dev` used to trigger
          // full rebuild storms (each storm recompiles ~1500 modules/route).
          "**/*.log",
          "**/*.tsbuildinfo",
          "**/.secrets/**",
          "**/.chroma/**",
        ],
        aggregateTimeout: 300,
        poll: false,
      };
    }
    return config;
  },
};

export default nextConfig;
