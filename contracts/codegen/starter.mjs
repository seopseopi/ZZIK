// Function-body surgery through the TypeScript parser; never a brace regex.
import ts from 'typescript';
import { readFileSync } from 'node:fs';
const input = JSON.parse(readFileSync(0, 'utf8'));
function functions(source) {
  const file = ts.createSourceFile(input.path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  if (file.parseDiagnostics.length) throw new Error('Invalid TypeScript source');
  return new Map(file.statements.filter(n => ts.isFunctionDeclaration(n) && n.name && n.body)
    .map(n => [n.name.text, {start: n.body.getStart(file), end: n.body.end}]));
}
const nodes = functions(input.source);
const reference = input.reference === undefined ? null : functions(input.reference);
const names = input.symbols === '*' ? [...nodes.keys()] : input.symbols;
if (!names.length || new Set(names).size !== names.length) throw new Error('Invalid/empty symbol list');
const edits = names.map(name => {
  if (!nodes.has(name) || (reference && !reference.has(name))) throw new Error(`Missing function ${name}`);
  const n = nodes.get(name), r = reference?.get(name);
  return {...n, text: r ? input.reference.slice(r.start, r.end) : `{ return ((): never => { throw new Error(${JSON.stringify(`ZZIK_STARTER:${input.id}:${name}`)}); })(); }`};
});
let source = input.source;
for (const edit of edits.sort((a,b) => b.start-a.start)) source = source.slice(0,edit.start) + edit.text + source.slice(edit.end);
process.stdout.write(JSON.stringify({source, symbols:names}));
