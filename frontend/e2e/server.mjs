// Static server for the built fixture site, behaving like GitHub Pages: directory URLs redirect to a
// trailing slash and serve index.html, and missing files get the site's 404.html with a 404 status.
// Usage: node e2e/server.mjs <root dir> <port>
import { createServer } from 'node:http'
import { readFile, stat } from 'node:fs/promises'
import { extname, join, normalize } from 'node:path'

const [root, port] = process.argv.slice(2)
const notFoundPage = join(root, 'the_list', '404.html')
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.txt': 'text/plain; charset=utf-8', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.png': 'image/png',
  '.woff2': 'font/woff2', '.ics': 'text/calendar; charset=utf-8',
}

async function isDir(path) {
  return (await stat(path).catch(() => null))?.isDirectory() ?? false
}

createServer(async (req, res) => {
  const { pathname, search } = new URL(req.url, 'http://localhost')
  let file = join(root, normalize(decodeURIComponent(pathname)))
  if (await isDir(file)) {
    if (!pathname.endsWith('/')) {
      res.writeHead(301, { Location: `${pathname}/${search}` }).end()
      return
    }
    file = join(file, 'index.html')
  }
  try {
    const body = await readFile(file)
    res.writeHead(200, { 'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream' }).end(body)
  } catch {
    res.writeHead(404, { 'Content-Type': TYPES['.html'] }).end(await readFile(notFoundPage).catch(() => 'Not found'))
  }
}).listen(Number(port), '127.0.0.1', () => console.log(`Serving ${root} on http://127.0.0.1:${port}/the_list/`))
