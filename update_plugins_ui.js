const fs = require('fs');
let html = fs.readFileSync('web/index.html', 'utf8');

const replacement = `                <label class="checkbox-item">
                    <input type="checkbox" id="normCheck"> 条件判断归一化 (Normalize)
                </label>
            </div>
            <div style="margin-top: 15px;">
                <input type="file" id="pluginUpload" accept=".wasm" style="display: none;">
                <button class="btn-mini" onclick="document.getElementById('pluginUpload').click()" style="padding: 6px 10px; width: 100%;">安装自定义插件 (WASM)</button>
            </div>
        </div>`;

html = html.replace(
    /                <label class="checkbox-item">\s*<input type="checkbox" id="normCheck"> 条件判断归一化 \(Normalize\)\s*<\/label>\s*<\/div>\s*<\/div>/,
    replacement
);

fs.writeFileSync('web/index.html', html);
console.log('updated plugin ui');
