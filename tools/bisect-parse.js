const fs = require('fs');
const path = require('path');
const vm = require('vm');

const filePath = path.resolve(__dirname, '..', 'campfirevalley', 'web', 'static', 'js', 'campfire-nodes.js');
const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);

function comp(end) {
  const code = lines.slice(0, end).join('\n');
  try {
    new vm.Script(code, { filename: 'campfire-nodes.js' });
    return true;
  } catch (e) {
    return false;
  }
}

let lo = 1, hi = lines.length, firstBad = null;
while (lo <= hi) {
  const mid = Math.floor((lo + hi) / 2);
  if (comp(mid)) {
    lo = mid + 1;
  } else {
    firstBad = mid;
    hi = mid - 1;
  }
}

if (firstBad === null) {
  console.log('No parse error detected');
} else {
  console.log('First failing line:', firstBad);
  const start = Math.max(1, firstBad - 5);
  for (let i = start; i <= firstBad + 2 && i <= lines.length; i++) {
    console.log(String(i).padStart(4), lines[i - 1]);
  }
}