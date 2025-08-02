# Frontend

This directory houses the React client built with Vite and TypeScript.

## Development

1. Install the project toolchain:
   ```bash
   mise install
   pnpm install
   ```
2. Start the Vite dev server which proxies API requests to Django:
   ```bash
   pnpm dev
   ```
   The application will be available at <http://localhost:5173>.

## Production Build

1. Create an optimized build:
   ```bash
   pnpm build
   ```
   Compiled assets will be written to `src/web/static/dist/` for Django or nginx to serve.
2. Optionally preview the build locally:
   ```bash
   pnpm preview
   ```

See `docs/frontend/architecture.md` for more details on the frontend stack.

## Tooling

The `scripts/` directory holds small Node helpers used by pre-commit:

- `format.mjs` formats files with Prettier. It detects whether the optional
  `prettier-plugin-tailwindcss` dependency is installed and only loads the
  plugin when available so commits do not fail on machines missing the plugin.
- `lint.mjs` runs ESLint if it has been installed. When the `node_modules`
  directory is absent the script exits without error, allowing contributions
  from environments that lack the JavaScript toolchain.

Both files use the `.mjs` extension to opt into Node's native ES module
support so they can use `import` syntax without transpilation.
