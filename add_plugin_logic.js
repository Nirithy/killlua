const fs = require('fs');
let html = fs.readFileSync('web/index.html', 'utf8');

const pluginVars = `
        let installedPlugins = [];

        // Handle Plugin Upload
        const pluginUpload = document.getElementById('pluginUpload');
        if (pluginUpload) {
            pluginUpload.addEventListener('change', async (e) => {
                const file = e.target.files[0];
                if (!file) return;

                try {
                    const arrayBuffer = await file.arrayBuffer();
                    const wasmModule = await WebAssembly.instantiate(arrayBuffer, {
                        env: {
                            memory: new WebAssembly.Memory({ initial: 256 })
                        }
                    });

                    const exports = wasmModule.instance.exports;

                    // Validate plugin interface
                    if (!exports.process || !exports.alloc_mem || !exports.free_mem || !exports.get_size || !exports.memory) {
                        alert('插件接口不兼容。需导出: alloc_mem, free_mem, process, get_size 和 memory');
                        return;
                    }

                    const pluginName = file.name.replace('.wasm', '');
                    const pluginId = 'plugin_' + Date.now();

                    installedPlugins.push({
                        id: pluginId,
                        name: pluginName,
                        exports: exports
                    });

                    // Add to UI
                    const cbGroup = document.querySelector('.checkbox-group');
                    const label = document.createElement('label');
                    label.className = 'checkbox-item';
                    label.innerHTML = \`<input type="checkbox" id="\${pluginId}"> [插件] \${pluginName}\`;
                    cbGroup.appendChild(label);

                    // Add listener for real-time update
                    document.getElementById(pluginId).onchange = scheduleUpdateDeobfuscation;

                    alert(\`插件 "\${pluginName}" 安装成功并已加入优化列表！\`);

                } catch (err) {
                    console.error(err);
                    alert('插件加载失败: ' + err.message);
                }

                // Clear input so same file can be selected again
                pluginUpload.value = '';
            });
        }

        // Apply plugins sequentially to bytecode
        function applyPlugins(bytecodeUint8) {
            let currentData = new Uint8Array(bytecodeUint8);

            for (const plugin of installedPlugins) {
                const checkbox = document.getElementById(plugin.id);
                if (checkbox && checkbox.checked) {
                    const exports = plugin.exports;
                    const memory = new Uint8Array(exports.memory.buffer);

                    const inLen = currentData.length;
                    const inPtr = exports.alloc_mem(inLen);

                    // Copy data to plugin memory
                    memory.set(currentData, inPtr);

                    // Process
                    const outPtr = exports.process(inPtr, inLen);
                    const outSize = exports.get_size();

                    // Read back
                    if (outSize > 0 && outPtr !== 0) {
                        const newMem = new Uint8Array(exports.memory.buffer);
                        currentData = new Uint8Array(newMem.slice(outPtr, outPtr + outSize));
                    }

                    exports.free_mem(inPtr);
                }
            }

            return currentData;
        }
`;

html = html.replace(
    /let currentFileName = "";/,
    'let currentFileName = "";\n' + pluginVars
);

// update updateDeobfuscation to call applyPlugins before deobfuscate
html = html.replace(
    /const result = LuaDeob\.deobfuscate\(currentBytecode, fold, dbe, sbm, dce, deflatten, rse, norm\);/g,
    `
                let processedBytecode = applyPlugins(currentBytecode);
                const result = LuaDeob.deobfuscate(processedBytecode, fold, dbe, sbm, dce, deflatten, rse, norm);`
);

fs.writeFileSync('web/index.html', html);
console.log('updated plugin logic');
