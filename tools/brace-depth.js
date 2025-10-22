const fs = require('fs');
const path = 'campfirevalley/web/static/js/campfire-nodes.js';
const src = fs.readFileSync(path, 'utf8');
const start = src.indexOf('const HexNodeBaseMixin =');
const end = src.indexOf('\n};', start) + 3;
const slice = src.slice(start, end);
let depth = 0;
let inStr = false;
let strChar = '';
let inLineComment = false;
let inBlockComment = false;
const lines = slice.split('\n');
for (let li = 0; li < lines.length; li++) {
  const line = lines[li];
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    const n = i + 1 < line.length ? line[i+1] : '';
    if (inLineComment) { /* handled per line end */ }
    if (inBlockComment) {
      if (c === '*' && n === '/') { inBlockComment = false; i++; }
      continue;
    }
    if (inStr) {
      if (c === '\\') { i++; continue; }
      if (c === strChar) { inStr = false; }
      continue;
    }
    if (c === '/' && n === '/') { inLineComment = true; break; }
    if (c === '/' && n === '*') { inBlockComment = true; i++; continue; }
    if (c === '\'' || c === '"' || c === '`') { inStr = true; strChar = c; continue; }
    if (c === '{') { depth++; }
    else if (c === '}') { depth--; }
  }
  if (inLineComment) inLineComment = false;
  console.log(`${li+1}: depth=${depth} :: ${line}`);
}