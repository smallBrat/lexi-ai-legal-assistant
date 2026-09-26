/** @type {import('next').NextConfig} */
const nextConfig = {
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
