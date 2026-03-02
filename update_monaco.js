const fs = require('fs');
let html = fs.readFileSync('web/index.html', 'utf8');

// 1. Replace text area with div
html = html.replace(
    /<textarea id="asmInput"[^>]*><\/textarea>/,
    '<div id="asmInput" style="width: 100%; height: 500px; border: 1px solid var(--border-color); border-radius: 4px;"></div>'
);

// 2. Add Monaco script tag right before <script> Let LuaDeob = null;
html = html.replace(
    /<!-- INSERT_JS_HERE -->/,
    `<!-- INSERT_JS_HERE -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs/loader.min.js"></script>`
);

// 3. Inject monaco init logic at the start of <script>
const initLogic = `
        let monacoEditor = null;

        require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs' }});
        require(['vs/editor/editor.main'], function() {
            monaco.languages.register({ id: 'lasm' });
            monaco.languages.setMonarchTokensProvider('lasm', {
                tokenizer: {
                    root: [
                        [/^\\s*\\d+:/, 'keyword'],  // PC
                        [/\\[.*?\\]/, 'number'],   // Brackets for line numbers/constants
                        [/\\b(MOVE|LOADK|LOADKX|LOADBOOL|LOADNIL|GETUPVAL|GETTABUP|GETTABLE|SETTABUP|SETUPVAL|SETTABLE|NEWTABLE|SELF|ADD|SUB|MUL|MOD|POW|DIV|IDIV|BAND|BOR|BXOR|SHL|SHR|UNM|BNOT|NOT|LEN|CONCAT|JMP|EQ|LT|LE|TEST|TESTSET|CALL|TAILCALL|RETURN|FORLOOP|FORPREP|TFORCALL|TFORLOOP|SETLIST|CLOSURE|VARARG|EXTRAARG)\\b/, 'keyword'], // Opcodes
                        [/;.*/, 'comment'], // Comments
                        [/\\b(R\\d+|U\\d+|K\\d+)\\b/, 'variable'], // Registers/Upvalues/Constants
                    ]
                }
            });

            monaco.editor.defineTheme('lasm-dark', {
                base: 'vs-dark',
                inherit: true,
                rules: [
                    { token: 'keyword', foreground: '569cd6' },
                    { token: 'number', foreground: 'b5cea8' },
                    { token: 'comment', foreground: '608b4e' },
                    { token: 'variable', foreground: '9cdcfe' }
                ],
                colors: {
                    'editor.background': '#1e1e1e'
                }
            });

            monacoEditor = monaco.editor.create(document.getElementById('asmInput'), {
                value: '-- 粘贴 .lasm 内容或点击下方上传',
                language: 'lasm',
                theme: 'lasm-dark',
                automaticLayout: true,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                fontSize: 14,
                fontFamily: "'Consolas', 'Monaco', 'Courier New', monospace"
            });
        });

        // Helper to set editor value safely
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
        }
`;

html = html.replace(
    /let LuaDeob = null;/,
    initLogic + '\n        let LuaDeob = null;'
);

// 4. Update references to get/set asmInput
html = html.replace(
    /document\.getElementById\('asmInput'\)\.value = re\.target\.result;/g,
    "setAsmInputValue(re.target.result);"
);
html = html.replace(
    /const content = document\.getElementById\('asmInput'\)\.value;/g,
    "const content = getAsmInputValue();"
);
html = html.replace(
    /document\.getElementById\('asmInput'\)\.value = asmContent;/g,
    "setAsmInputValue(asmContent);"
);

fs.writeFileSync('web/index.html', html);
console.log('updated');
