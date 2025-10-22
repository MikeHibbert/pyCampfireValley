const fs = require('fs');
const vm = require('vm');
const path = require('path');

const filePath = path.resolve(__dirname, '..', 'campfirevalley', 'web', 'static', 'js', 'campfire-nodes.js');
const code = fs.readFileSync(filePath, 'utf8');

try {
  // Use vm.Script to produce accurate line/column locations
  const script = new vm.Script(code, { filename: 'campfire-nodes.js' });
  script.runInThisContext();
  console.log('OK: campfire-nodes.js compiled without syntax errors');
} catch (e) {
  console.error('FAIL: Syntax error compiling campfire-nodes.js');
  console.error(String(e));
  // Try to extract line and column if available
  if (e.stack) {
    const m = e.stack.match(/campfire-nodes.js:(\d+):(\d+)/);
    if (m) {
      const line = parseInt(m[1], 10);
      const col = parseInt(m[2], 10);
      const lines = code.split(/\r?\n/);
      const context = [];
      for (let i = Math.max(0, line - 4); i < Math.min(lines.length, line + 2); i++) {
        context.push(`${i + 1}: ${lines[i]}`);
      }
      console.error('Context around error:');
      console.error(context.join('\n'));
      console.error(`--> line ${line}, column ${col}`);
      // Extra debug: show the exact character and code at the location
      const targetLine = lines[line - 1] || '';
      const char = targetLine[col - 1] || '';
      const codePoint = char ? char.codePointAt(0) : null;
      console.error(`Char at location: '${char}' (codePoint: ${codePoint})`);
      const snippet = targetLine.slice(Math.max(0, col - 20), col + 20);
      console.error(`Snippet near location: ${snippet}`);
    }
  }
  process.exit(1);
}