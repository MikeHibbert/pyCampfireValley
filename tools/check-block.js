const fs = require('fs');
const path = 'campfirevalley/web/static/js/campfire-nodes.js';
const src = fs.readFileSync(path, 'utf8');
const start = src.indexOf('onDrawForeground: function(ctx)');
const end = src.indexOf('\n    },', start); // property end
const slice = src.slice(start, end+6);
const lines = slice.split('\n');
let depth = 0;
let inStr=false,strChar='';
let inLine=false,inBlock=false;
const stack = [];
function push(li, i){ stack.push({li: li+1, col: i+1, text: lines[li]}); }
function pop(li, i){ const open = stack.pop(); console.log(`close } at ${li+1}:${i+1} for open { at ${open.li}:${open.col} -> ${open.text.trim()}`); }
for(let li=0; li<lines.length; li++){
  const line = lines[li];
  for(let i=0;i<line.length;i++){
    const c=line[i], n=line[i+1]||'';
    if(inLine){break;}
    if(inBlock){ if(c==='*' && n=== '/') { inBlock=false; i++; } continue; }
    if(inStr){ if(c==='\\'){ i++; continue; } if(c===strChar){inStr=false;} continue; }
    if(c==='/' && n=== '/') { inLine=true; break; }
    if(c==='/' && n==='*') { inBlock=true; i++; continue; }
    if(c==='\''||c==='"'||c==='`'){ inStr=true; strChar=c; continue; }
    if(c==='{'){ depth++; push(li,i); }
    else if(c==='}'){ depth--; pop(li,i); }
  }
  if(inLine) inLine=false;
}
console.log('Remaining opens', stack.length);
for(const s of stack){ console.log(`Unclosed { at ${s.li}:${s.col} -> ${s.text.trim()}`); }