const fs = require('fs');
let html = fs.readFileSync('web/index.html', 'utf8');

const regex = /id="pluginUpload"/;
if(regex.test(html)) {
    console.log("Success: pluginUpload input found");
} else {
    console.log("Failed: pluginUpload input not found");
}

const btnRegex = />安装自定义插件 \(WASM\)<\/button>/;
if(btnRegex.test(html)) {
    console.log("Success: install button found");
} else {
    console.log("Failed: install button not found");
}
