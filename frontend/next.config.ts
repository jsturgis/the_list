import type { NextConfig } from "next";

// The Deploy workflow passes the base path and URL GitHub Pages reports (actions/configure-pages): "" and
// https://list.sturgis.me with the custom domain, "/the_list" and https://jsturgis.github.io/the_list
// without it. Local builds and tests default to /the_list.
const basePath = process.env.PAGES_BASE_PATH ?? "/the_list";
const siteUrl = process.env.PAGES_SITE_URL || `https://jsturgis.github.io${basePath}`;

const nextConfig: NextConfig = {
  output: "export",
  basePath,
  // Every page is a directory index (bands/10/index.html), so refreshing any URL loads it.
  trailingSlash: true,
  // Links get the base path automatically; this is for the URLs built by hand (fetch, history).
  // NEXT_PUBLIC_SITE_URL: absolute links to the site (used in calendar events).
  env: { NEXT_PUBLIC_BASE_PATH: basePath, NEXT_PUBLIC_SITE_URL: siteUrl },
};

export default nextConfig;
