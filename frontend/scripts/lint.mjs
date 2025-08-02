/**
 * Execute ESLint if it is available.
 *
 * The script is invoked by pre-commit and uses the `.mjs` extension so it can
 * leverage modern ES module syntax. We look for the ESLint binary under
 * `node_modules`. If it is missing (for example, a developer has not installed
 * Node dependencies) the script exits successfully so commits can still
 * proceed. When the binary exists, ESLint is spawned with the arguments passed
 * from pre-commit and the exit code is forwarded to the calling process.
 */

// Test for the presence of the ESLint binary
import { existsSync } from 'node:fs'
// Spawn ESLint as a child process
import { spawnSync } from 'node:child_process'
// Resolve the path to this script on disk
import { fileURLToPath } from 'node:url'
// Build filesystem paths
import { dirname, join } from 'node:path'

// Directory containing this script
const root = dirname(fileURLToPath(import.meta.url))
// Expected location of the ESLint executable
const eslintBin = join(root, '..', 'node_modules', '.bin', 'eslint')

// If ESLint isn't installed, silently skip linting
if (!existsSync(eslintBin)) {
  process.exit(0)
}

// Run ESLint with the provided arguments and forward its exit code
const result = spawnSync(eslintBin, process.argv.slice(2), { stdio: 'inherit' })
process.exit(result.status ?? 1)
