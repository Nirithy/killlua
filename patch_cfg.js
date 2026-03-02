const fs = require('fs');

let html = fs.readFileSync('web/index.html', 'utf8');

// 1. Add cfg-controls div
html = html.replace('<p style="color: #333">尚未生成控制流图</p>', '<p style="color: #333">尚未生成控制流图</p>'); // just sanity check

const cfgControls = `
            <div id="cfg-controls" style="padding: 10px; background: var(--sidebar-bg); border-top: 1px solid var(--border-color); display: flex; gap: 10px; align-items: center;">
                <button class="btn-mini" id="cfgSaveImgBtn" style="padding: 8px 15px;">保存当前流程图</button>
                <button class="btn-mini" id="cfgApplyChangesBtn" style="padding: 8px 15px;">保存流程图的改动</button>
                <button class="btn-mini" id="cfgToAsmBtn" style="padding: 8px 15px; background: #e67e22;">将流程图的改动转换为LASM</button>
                <div style="flex-grow: 1;"></div>
                <input type="text" id="cfgSearchInput" placeholder="搜索节点 (ID 或内容)..." style="padding: 6px; border-radius: 4px; border: 1px solid var(--border-color); background: var(--panel-bg); color: var(--text-color);">
                <button class="btn-mini" id="cfgSearchBtn" style="padding: 8px 15px;">查</button>
            </div>
`;

if (!html.includes('id="cfg-controls"')) {
    html = html.replace('</div>\n        </div>\n\n        <div id="cfg-dot"', '</div>\n' + cfgControls + '        </div>\n\n        <div id="cfg-dot"');
}

// 2. Add manipulation: { enabled: true } to options
html = html.replace('interaction: {', 'manipulation: { enabled: true },\n                    interaction: {');

// 3. Make data and network accessible globally
html = html.replace('const network = new vis.Network(container, data, options);', 'const network = new vis.Network(container, data, options);\n                window.cfgNetwork = network;\n                window.cfgData = data;');

// 4. Modify network.on("doubleClick") saveBtn.onclick logic
const oldSaveLogic = `saveBtn.onclick = () => {
                            const newLabel = textarea.value;
                            data.nodes.update({ id: nodeId, label: newLabel });

                            // To actually integrate with compilation, we take all node labels,
                            // order them, and construct an ASM string.
                            const allNodes = data.nodes.get();
                            allNodes.sort((a,b) => parseInt(a.id) - parseInt(b.id));
                            let asmContent = "";
                            allNodes.forEach(n => {
                                // Extract just the instructions, ignoring the "BBx [PC y-z]" header
                                const parts = n.label.split('\\n');
                                parts.slice(1).forEach(p => {
                                    // Remove the "PC: " prefix
                                    const codeMatch = p.match(/^\\d+:\\s*(.*)/);
                                    if (codeMatch) asmContent += codeMatch[1] + "\\n";
                                    else asmContent += p + "\\n";
                                });
                            });

                            setAsmInputValue(asmContent);
                            // Switch to ASM tab automatically
                            document.querySelector('.tab[data-tab="asm"]').click();
                            closeEditor();
                        };`;

const newSaveLogic = `saveBtn.onclick = () => {
                            const newLabel = textarea.value;
                            data.nodes.update({ id: nodeId, label: newLabel });
                            closeEditor();
                        };`;

html = html.replace(oldSaveLogic, newSaveLogic);


// 5. Add event listeners for new buttons right after network.on doubleClick setup
const cfgButtonLogic = `
                // Setup CFG Controls
                document.getElementById('cfgSaveImgBtn').onclick = () => {
                    const canvas = document.querySelector('#cfg-container canvas');
                    if (canvas) {
                        const url = canvas.toDataURL('image/png');
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = 'cfg_' + Date.now() + '.png';
                        a.click();
                    } else {
                        alert("无法找到流程图画布");
                    }
                };

                document.getElementById('cfgApplyChangesBtn').onclick = () => {
                    alert("改动已保存在内存中");
                };

                document.getElementById('cfgToAsmBtn').onclick = () => {
                    if (!window.cfgData) return;
                    const allNodes = window.cfgData.nodes.get();
                    allNodes.sort((a,b) => parseInt(a.id) - parseInt(b.id));
                    let asmContent = "";
                    allNodes.forEach(n => {
                        const parts = n.label.split('\\n');
                        parts.slice(1).forEach(p => {
                            const codeMatch = p.match(/^\\d+:\\s*(.*)/);
                            if (codeMatch) asmContent += codeMatch[1] + "\\n";
                            else asmContent += p + "\\n";
                        });
                    });
                    setAsmInputValue(asmContent);
                    document.querySelector('.tab[data-tab="asm"]').click();
                };

                document.getElementById('cfgSearchBtn').onclick = () => {
                    const query = document.getElementById('cfgSearchInput').value.toLowerCase();
                    if (!query || !window.cfgData || !window.cfgNetwork) return;

                    const nodes = window.cfgData.nodes.get();
                    let foundId = null;

                    for (const n of nodes) {
                        if (String(n.id).toLowerCase() === query || (n.label && n.label.toLowerCase().includes(query))) {
                            foundId = n.id;
                            break;
                        }
                    }

                    if (foundId !== null) {
                        window.cfgNetwork.selectNodes([foundId]);
                        window.cfgNetwork.focus(foundId, { scale: 1.2, animation: true });
                    } else {
                        alert("未找到匹配的节点");
                    }
                };
`;

html = html.replace('} catch (e) {', cfgButtonLogic + '\n            } catch (e) {');


fs.writeFileSync('web/index.html', html);
