/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "cdn.bfl.ml" },
      { protocol: "https", hostname: "api.bfl.ml" },
    ],
  },
};

module.exports = nextConfig;
