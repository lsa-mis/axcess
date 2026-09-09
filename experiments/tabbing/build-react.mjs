// Build only the vendored reference fixture, using Axcess's locked dependencies.
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { writeFileSync } from 'node:fs';

const require = createRequire(new URL('../../src/audit/web/frontend/package.json', import.meta.url));
const esbuild = require('esbuild');
const fixture = new URL('./fixtures/upstream/react/', import.meta.url);
await esbuild.build({
  entryPoints: [fileURLToPath(new URL('app.jsx', fixture))],
  outfile: fileURLToPath(new URL('app.js', fixture)),
  nodePaths: [fileURLToPath(new URL('../../src/audit/web/frontend/node_modules', import.meta.url))],
  bundle: true,
  format: 'iife',
  jsx: 'automatic',
  minify: true,
  legalComments: 'inline',
  define: { 'process.env.NODE_ENV': '"production"' },
  banner: { js: '// Generated for the Axcess tabbing experiment; source: app.jsx. See ../../../UPSTREAM.md.' },
});
writeFileSync(new URL('build.json', fixture), JSON.stringify({
  node: process.version,
  esbuild: esbuild.version,
  react: require('react/package.json').version,
  react_dom: require('react-dom/package.json').version,
  command: 'node experiments/tabbing/build-react.mjs',
}, null, 2) + '\n');
