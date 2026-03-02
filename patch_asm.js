const fs = require('fs');

let html = fs.readFileSync('web/index.html', 'utf8');

// 1. Replace #asmInput div
html = html.replace(
    '<div id="asmInput" style="width: 100%; height: 500px; border: 1px solid var(--border-color); border-radius: 4px;"></div>',
    '<div id="asmBlocksContainer" style="display:flex; flex-direction:column; gap:10px; overflow-y:auto; height: 500px; padding: 10px; border: 1px solid var(--border-color); border-radius: 4px;"></div>'
);


// 2. Remove old monaco editor initialization inside require
const oldMonacoInit = `            monacoEditor = monaco.editor.create(document.getElementById('asmInput'), {
                value: '-- 粘贴 .lasm 内容或点击下方上传',
                language: 'lasm',
                theme: 'lasm-dark',
                automaticLayout: true,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                fontSize: 14,
                fontFamily: "'Consolas', 'Monaco', 'Courier New', monospace"
            });`;

html = html.replace(oldMonacoInit, `            // monaco is loaded, initial blocks will just use normal DOM until clicked
            if (window._pendingAsmContent) {
                setAsmInputValue(window._pendingAsmContent);
                window._pendingAsmContent = null;
            } else {
                setAsmInputValue('-- 粘贴 .lasm 内容或点击下方上传');
            }`);

// 3. Rewrite setAsmInputValue and getAsmInputValue
const oldFuncs = `        // Helper to set editor value safely
        function setAsmInputValue(val) {
            if (monacoEditor) {
                monacoEditor.setValue(val);
            } else {
                // fallback if not loaded yet
                setTimeout(() => setAsmInputValue(val), 100);
            }
        }

        function getAsmInputValue() {
            return monacoEditor ? monacoEditor.getValue() : '';
        }`;

const newFuncs = `        // Block-based ASM rendering
        let activeMonacoEditor = null;
        let activeEditorBlockId = null;

        function setAsmInputValue(val) {
            if (typeof monaco === 'undefined') {
                window._pendingAsmContent = val;
                return;
            }
            const container = document.getElementById('asmBlocksContainer');
            if (!container) return;
            container.innerHTML = '';

            // Clean up any active editor
            if (activeMonacoEditor) {
                activeMonacoEditor.dispose();
                activeMonacoEditor = null;
            }

            // Split by basic heuristic (e.g. empty lines or labels). Let's use empty lines as primary block separators for LASM
            const blocks = val.split(/\\n\\s*\\n/);

            blocks.forEach((blockText, index) => {
                if (!blockText.trim()) return;

                const blockDiv = document.createElement('div');
                blockDiv.className = 'asm-block';
                blockDiv.id = 'asm-block-' + index;
                blockDiv.style.background = 'var(--code-bg)';
                blockDiv.style.border = '1px solid #555';
                blockDiv.style.borderRadius = '4px';
                blockDiv.style.padding = '10px';
                blockDiv.style.position = 'relative';

                const pre = document.createElement('pre');
                pre.innerText = blockText;
                pre.style.margin = '0';
                pre.style.whiteSpace = 'pre-wrap';
                pre.style.cursor = 'pointer';
                pre.title = '点击编辑此块';

                blockDiv.appendChild(pre);

                // Edit mode toggle
                pre.onclick = () => {
                    if (activeMonacoEditor) {
                        // Save previous
                        const prevDiv = document.getElementById(activeEditorBlockId);
                        if (prevDiv) {
                            const prevPre = prevDiv.querySelector('pre');
                            prevPre.innerText = activeMonacoEditor.getValue();
                            prevPre.style.display = 'block';
                            const ec = prevDiv.querySelector('.editor-container');
                            if(ec) ec.remove();
                            const sc = prevDiv.querySelector('.save-btn-container');
                            if(sc) sc.remove();
                        }
                        activeMonacoEditor.dispose();
                    }

                    pre.style.display = 'none';
                    activeEditorBlockId = blockDiv.id;

                    const editorContainer = document.createElement('div');
                    editorContainer.className = 'editor-container';
                    editorContainer.style.height = '200px';
                    blockDiv.appendChild(editorContainer);

                    const saveContainer = document.createElement('div');
                    saveContainer.className = 'save-btn-container';
                    saveContainer.style.display = 'flex';
                    saveContainer.style.justifyContent = 'flex-end';
                    saveContainer.style.marginTop = '5px';

                    const saveBtn = document.createElement('button');
                    saveBtn.innerText = '保存该块';
                    saveBtn.className = 'btn-mini';
                    saveContainer.appendChild(saveBtn);
                    blockDiv.appendChild(saveContainer);

                    activeMonacoEditor = monaco.editor.create(editorContainer, {
                        value: pre.innerText,
                        language: 'lasm',
                        theme: 'lasm-dark',
                        automaticLayout: true,
                        minimap: { enabled: false },
                        scrollBeyondLastLine: false,
                        fontSize: 14
                    });

                    saveBtn.onclick = (e) => {
                        e.stopPropagation();
                        pre.innerText = activeMonacoEditor.getValue();
                        pre.style.display = 'block';
                        editorContainer.remove();
                        saveContainer.remove();
                        activeMonacoEditor.dispose();
                        activeMonacoEditor = null;
                        activeEditorBlockId = null;
                    };
                };

                container.appendChild(blockDiv);
            });
        }

        function getAsmInputValue() {
            const container = document.getElementById('asmBlocksContainer');
            if (!container) return '';

            // If an editor is currently open, save its content back to the PRE first
            if (activeMonacoEditor && activeEditorBlockId) {
                const activeDiv = document.getElementById(activeEditorBlockId);
                if (activeDiv) {
                    const activePre = activeDiv.querySelector('pre');
                    activePre.innerText = activeMonacoEditor.getValue();
                }
            }

            let fullText = [];
            container.querySelectorAll('.asm-block pre').forEach(pre => {
                fullText.push(pre.innerText);
            });
            return fullText.join('\\n\\n');
        }`;

html = html.replace(oldFuncs, newFuncs);

fs.writeFileSync('web/index.html', html);
