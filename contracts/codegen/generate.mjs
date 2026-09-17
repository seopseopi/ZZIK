import openapiTS, { astToString } from 'openapi-typescript';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';

const schema = new URL('../openapi.json', import.meta.url);
const destination = new URL('../../frontend/src/generated/api.d.ts', import.meta.url);
const output = '// Generated from contracts/openapi.json. Run npm run types:generate; do not edit.\n' + astToString(await openapiTS(schema));
if (process.argv.includes('--check')) {
  let current = '';
  try { current = readFileSync(destination, 'utf8'); } catch { /* Missing output is stale. */ }
  if (current !== output) {
    console.error('Frontend API types are stale. Review the API contract, then run npm run types:generate.');
    process.exit(1);
  }
  console.log('Frontend types match OpenAPI.');
} else {
  mkdirSync(new URL('.', destination), { recursive: true });
  writeFileSync(destination, output);
  console.log('Generated frontend/src/generated/api.d.ts');
}
