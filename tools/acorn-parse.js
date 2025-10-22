const fs = require('fs');
const path = require('path');
const acorn = require('acorn');

const filePath = path.resolve(__dirname, '..', 'campfirevalley', 'web', 'static', 'js', 'campfire-nodes.js');
const code = fs.readFileSync(filePath, 'utf8');

try {
  acorn.parse(code, { ecmaVersion: 'latest', sourceType: 'script', locations: true });
  console.log('OK: acorn parsed campfire-nodes.js');
} catch (e) {
  console.error('Acorn parse error:', e.message);
  if (e.loc) {
    const { line, column } = e.loc;
    const lines = code.split(/\r?\n/);
    const ctx = [];
    for (let i = Math.max(0, line - 4); i < Math.min(lines.length, line + 2); i++) {
      ctx.push(`${i + 1}: ${lines[i]}`);
    }
    console.error(ctx.join('\n'));
    console.error(`--> line ${line}, column ${column}`);
  }
}