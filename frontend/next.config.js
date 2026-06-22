/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return {
      // afterFiles: Next.js checks local Route Handlers first, then falls through
      // to this rewrite if no handler matches — so mock routes in app/api/ work.
      afterFiles: [
        {
          source: "/api/v1/:path*",
          destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/:path*`,
        },
      ],
    }
  },
};

module.exports = nextConfig;
