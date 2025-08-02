/**
 * Format files with Prettier while gracefully handling the optional
 * Tailwind plugin.
 *
 * The file uses the `.mjs` extension so Node treats it as an ES module and
 * allows `import` statements without needing to transpile. Pre-commit passes
 * a list of staged files to this script. We resolve those paths relative to
 * the frontend directory and invoke Prettier. If the Tailwind CSS plugin is
 * installed it is included so class names are sorted; otherwise Prettier runs
 * without it to avoid failing when contributors have not installed all Node
 * dependencies.
 */

// Run Prettier as a subprocess
import { execSync } from 'node:child_process'
// Detect whether the Tailwind plugin exists
import { existsSync } from 'node:fs'
// Normalize file paths
import { resolve, relative } from 'node:path'

// Location of the frontend directory
const base = new URL('..', import.meta.url).pathname
// Path where the plugin would be installed
const plugin = `${base}/node_modules/prettier-plugin-tailwindcss`
// Determine if the plugin is available
const hasPlugin = existsSync(plugin)

// Collect files passed on the command line and make paths relative to `base`
const files = process.argv
  .slice(2) // skip "node" and script name
  .map((f) => {
    const abs = resolve(f)
    const rel = relative(base, abs)
    // When pre-commit runs from the repo root it prefixes paths with
    // "frontend/"; remove that so Prettier sees paths relative to `base`.
    return rel.startsWith('frontend/') ? rel.slice('frontend/'.length) : rel
  })
  .join(' ')

// Only invoke Prettier if files were provided
if (files) {
  // Include the Tailwind plugin when available
  const cmd = hasPlugin
    ? `prettier --plugin prettier-plugin-tailwindcss --write ${files}`
    : `prettier --write ${files}`
  execSync(cmd, { stdio: 'inherit', cwd: base })
}
