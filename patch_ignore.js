const fs = require('fs');
let html = fs.readFileSync('web/index.html', 'utf-8');

const htmlControlsSearch = `<div class="checkbox-group">
                <label class="checkbox-item">
                    <input type="checkbox" id="foldCheck"> 常量折叠 (Folding)
                </label>`;

const htmlControlsReplace = `<div class="control-group" style="margin-bottom: 10px;">
            <label>过滤/忽略指令 (逗号分隔)</label>
            <input type="text" id="ignoreOpcodes" placeholder="如: MOVE, TESTSET" style="width: 100%; padding: 6px; border-radius: 4px; border: 1px solid var(--border-color); background: var(--panel-bg); color: var(--text-color); box-sizing: border-box;">
        </div>
        <div class="checkbox-group">
                <label class="checkbox-item">
                    <input type="checkbox" id="foldCheck"> 常量折叠 (Folding)
                </label>`;

if (html.includes(htmlControlsSearch)) {
    html = html.replace(htmlControlsSearch, htmlControlsReplace);
} else {
    console.log("Could not find HTML controls to patch");
}

const renderDisasmSearch = `        function renderCollapsibleDisasm(text, containerId) {`;
const renderDisasmReplace = `        function renderCollapsibleDisasm(text, containerId) {
            const ignoreInput = document.getElementById('ignoreOpcodes');
            const ignoreList = ignoreInput ? ignoreInput.value.split(',').map(s => s.trim().toUpperCase()).filter(s => s) : [];
`;

if (html.includes(renderDisasmSearch)) {
    html = html.replace(renderDisasmSearch, renderDisasmReplace);
} else {
    console.log("Could not find renderCollapsibleDisasm to patch");
}

const inFuncSearch = `                } else {
                    if (inFunc) {
                        currentFuncBody.push(line);
                    } else {`;
const inFuncReplace = `                } else {
                    if (inFunc) {
                        if (ignoreList.length > 0) {
                            const trimmed = line.trim();
                            if (!trimmed.startsWith(':goto_') && !trimmed.startsWith('.local') && !trimmed.startsWith('.upval') && !trimmed.startsWith('.line')) {
                                const op = trimmed.split(/\\s+/)[0];
                                if (ignoreList.includes(op)) {
                                    continue;
                                }
                            }
                        }
                        currentFuncBody.push(line);
                    } else {`;

if (html.includes(inFuncSearch)) {
    html = html.replace(inFuncSearch, inFuncReplace);
} else {
    console.log("Could not find inFunc block to patch");
}

const bindEventSearch = `        ['foldCheck', 'dbeCheck', 'sbmCheck', 'dceCheck', 'deflattenCheck', 'rseCheck', 'normCheck'].forEach(id => {
            document.getElementById(id).onchange = scheduleUpdateDeobfuscation;
        });`;
const bindEventReplace = `        ['foldCheck', 'dbeCheck', 'sbmCheck', 'dceCheck', 'deflattenCheck', 'rseCheck', 'normCheck'].forEach(id => {
            document.getElementById(id).onchange = scheduleUpdateDeobfuscation;
        });
        const ignoreInput = document.getElementById('ignoreOpcodes');
        if (ignoreInput) {
            ignoreInput.addEventListener('input', () => {
                if (window.lastDisassemblyResult) {
                    renderCollapsibleDisasm(window.lastDisassemblyResult.original, 'originalDisasm');
                    renderCollapsibleDisasm(window.lastDisassemblyResult.optimized, 'optimizedDisasm');
                } else if (originalBytecode) {
                    scheduleUpdateDeobfuscation();
                }
            });
        }`;

if (html.includes(bindEventSearch)) {
    html = html.replace(bindEventSearch, bindEventReplace);
} else {
    console.log("Could not find bindEvent to patch");
}

const saveDisasmSearch = `                    renderCollapsibleDisasm(result.disassembly, 'optimizedDisasm');
                    document.getElementById('cfgDotOutput').innerText = result.dot;`;
const saveDisasmReplace = `                    if (!window.lastDisassemblyResult) window.lastDisassemblyResult = {};
                    window.lastDisassemblyResult.optimized = result.disassembly;
                    renderCollapsibleDisasm(result.disassembly, 'optimizedDisasm');
                    document.getElementById('cfgDotOutput').innerText = result.dot;`;

if (html.includes(saveDisasmSearch)) {
    html = html.replace(saveDisasmSearch, saveDisasmReplace);
} else {
    console.log("Could not find saveDisasm optimized to patch");
}

const saveOrigDisasmSearch = `                        renderCollapsibleDisasm(result.disassembly, 'originalDisasm');
                        updateDeobfuscation();`;
const saveOrigDisasmReplace = `                        if (!window.lastDisassemblyResult) window.lastDisassemblyResult = {};
                        window.lastDisassemblyResult.original = result.disassembly;
                        renderCollapsibleDisasm(result.disassembly, 'originalDisasm');
                        updateDeobfuscation();`;

if (html.includes(saveOrigDisasmSearch)) {
    html = html.replace(saveOrigDisasmSearch, saveOrigDisasmReplace);
} else {
    console.log("Could not find saveDisasm original to patch");
}

fs.writeFileSync('web/index.html', html);
console.log("Patched ignoring opcodes.");
