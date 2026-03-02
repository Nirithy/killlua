const fs = require('fs');
let html = fs.readFileSync('web/index.html', 'utf8');

// I also need to update the base disassembly generation in fileInput.onchange
let match = html.match(/const result = LuaDeob\.deobfuscate\(currentBytecode, false, false, false, false, false, false, false\);/);
if (match) {
    let replaced = match[0].replace(
        "const result = LuaDeob.deobfuscate(currentBytecode, false, false, false, false, false, false, false);",
        "const processedBytecode = applyPlugins(currentBytecode);\n                    const result = LuaDeob.deobfuscate(processedBytecode, false, false, false, false, false, false, false);"
    );
    html = html.replace(match[0], replaced);
}

fs.writeFileSync('web/index.html', html);
console.log('updated base deobfuscate in fileInput');
