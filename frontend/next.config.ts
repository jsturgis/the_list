import type { NextConfig } from "next";

// GitHub Pages serves the site from https://<owner>.github.io/the_list/.
const basePath = "/the_list";

const nextConfig: NextConfig = {
  output: "export",
  basePath,
  // Every page is a directory index (bands/10/index.html), so refreshing any URL loads it.
  trailingSlash: true,
  // Links get the base path automatically; this is for the URLs built by hand (fetch, history).
  // NEXT_PUBLIC_SITE_URL: absolute links to the site (used in calendar events).
  env: { NEXT_PUBLIC_BASE_PATH: basePath, NEXT_PUBLIC_SITE_URL: `https://jsturgis.github.io${basePath}` },
};

export default nextConfig;
