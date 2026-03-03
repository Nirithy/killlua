const fs = require('fs');
let html = fs.readFileSync('web/index.html', 'utf-8');

const monacoValidationSearch = `                    saveBtn.onclick = (e) => {
                        e.stopPropagation();
                        pre.innerText = activeMonacoEditor.getValue();
                        pre.style.display = 'block';
                        editorContainer.remove();
                        saveContainer.remove();
                        activeMonacoEditor.dispose();
                        activeMonacoEditor = null;
                        activeEditorBlockId = null;
                    };`;

const monacoValidationReplace = `                    saveBtn.onclick = (e) => {
                        e.stopPropagation();

                        // Basic syntax check
                        const content = activeMonacoEditor.getValue();
                        const lines = content.split('\\n');
                        const errors = [];
                        let inFunc = false;

                        // Check jump labels
                        const definedLabels = new Set();
                        const usedLabels = new Set();

                        lines.forEach((l, idx) => {
                            const t = l.trim();
                            if (t.startsWith(':')) {
                                definedLabels.add(t.split(' ')[0]);
                            } else if (t.includes('goto ')) {
                                const parts = t.split(/\\s+/);
                                const lbl = parts[parts.indexOf('goto') + 1];
                                if (lbl) usedLabels.add(lbl);
                            } else if (t.match(/^\\d+:\\s*JMP\\s+/)) {
                                const parts = t.split(/\\s+/);
                                const lbl = parts[parts.length - 1];
                                if (lbl.startsWith(':')) usedLabels.add(lbl);
                            }
                        });

                        for (let ul of usedLabels) {
                            if (!definedLabels.has(ul)) {
                                errors.push(\`引用了未定义的标签: \${ul}\`);
                            }
                        }

                        if (errors.length > 0) {
                            if (!confirm("代码存在以下潜在问题，确定要保存吗？\\n" + errors.join("\\n"))) {
                                return;
                            }
                        }

                        pre.innerText = activeMonacoEditor.getValue();
                        pre.style.display = 'block';
                        editorContainer.remove();
                        saveContainer.remove();
                        activeMonacoEditor.dispose();
                        activeMonacoEditor = null;
                        activeEditorBlockId = null;
                    };`;

if (html.includes(monacoValidationSearch)) {
    html = html.replace(monacoValidationSearch, monacoValidationReplace);
    fs.writeFileSync('web/index.html', html);
    console.log("Patched Monaco Editor validation successfully.");
} else {
    console.log("Could not find Monaco save button to patch.");
}
