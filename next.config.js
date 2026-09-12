/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable React strict mode for development
  reactStrictMode: true,
  async headers() {
    return [{ source: '/sw.js', headers: [
      { key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' },
      { key: 'Service-Worker-Allowed', value: '/' },
    ] }]
  },

  // Enable SWC minification (faster than Terser)
  swcMinify: true,

  // Configure webpack to handle fallbacks for server-side modules
  webpack: (config, { isServer }) => {
    config.resolve.fallback = {
      ...config.resolve.fallback,
      fs: false,
      path: false,
      os: false,
    };
    return config;
  },

  // Image optimization
  images: {
    unoptimized: false,
  },

  // Production source maps (optional, for debugging)
  productionBrowserSourceMaps: false,
}

module.exports = nextConfig
