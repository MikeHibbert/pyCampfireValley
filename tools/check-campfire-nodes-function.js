const fs = require('fs');
const path = require('path');

const filePath = path.resolve(__dirname, '..', 'campfirevalley', 'web', 'static', 'js', 'campfire-nodes.js');
const code = fs.readFileSync(filePath, 'utf8');

try {
  // Use Function constructor as an alternative parser
  new Function(code);
  console.log('OK: campfire-nodes.js compiled (Function constructor)');
} catch (e) {
  console.error('FAIL (Function):', e.message);
  if (e.stack) console.error(e.stack);
}