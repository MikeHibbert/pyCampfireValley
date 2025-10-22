const fs = require('fs');
const vm = require('vm');
const path = require('path');

const baseDir = path.resolve(__dirname, '..', 'campfirevalley', 'web', 'static', 'js');
const files = [
  'litegraph.js',
  'gamification.js',
  'campfire-nodes.js',
  'litegraph-integration.js',
  'metrics.js',
  'main.js',
  'visualization.js'
];

function checkFile(fname) {
  const filePath = path.join(baseDir, fname);
  const code = fs.readFileSync(filePath, 'utf8');
  try {
    const script = new vm.Script(code, { filename: fname });
    script.runInThisContext();
    console.log(`OK: ${fname}`);
  } catch (e) {
    console.error(`FAIL: ${fname} -> ${e.message}`);
    if (e.stack) {
      const m = e.stack.match(new RegExp(`${fname.replace(/[-\\^$*+?.()|[\]{}]/g, '\\$&')}` + ':(\\d+):(\\d+)'));
      if (m) {
        const line = parseInt(m[1], 10);
        const col = parseInt(m[2], 10);
        const lines = code.split(/\r?\n/);
        const ctx = [];
        for (let i = Math.max(0, line - 4); i < Math.min(lines.length, line + 2); i++) {
          ctx.push(`${i + 1}: ${lines[i]}`);
        }
        console.error(ctx.join('\n'));
        console.error(`--> line ${line}, column ${col}`);
      }
    }
  }
}

files.forEach(checkFile);