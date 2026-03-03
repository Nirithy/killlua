const fs = require('fs');
let html = fs.readFileSync('web/index.html', 'utf8');

const warningCode = `                const parsedData = vis.network.convertDot(unescapedDot);

                let warnElement = null;
                if (parsedData.nodes.length > 500) {
                    warnElement = document.createElement('div');
                    warnElement.style.position = 'absolute';
                    warnElement.style.top = '10px';
                    warnElement.style.left = '50%';
                    warnElement.style.transform = 'translateX(-50%)';
                    warnElement.style.background = '#fff3cd';
                    warnElement.style.color = '#856404';
                    warnElement.style.padding = '10px 20px';
                    warnElement.style.borderRadius = '4px';
                    warnElement.style.border = '1px solid #ffeeba';
                    warnElement.style.zIndex = '1000';
                    warnElement.style.boxShadow = '0 2px 4px rgba(0,0,0,0.2)';
                    warnElement.innerHTML = \`<strong>警告：</strong> 当前控制流图节点数 (\${parsedData.nodes.length}) 超过 500，渲染可能会很慢或导致浏览器卡顿。建议在上方选择单个函数查看 CFG。\`;
                    // Note: We'll append it to container after the network is created or wrap the container
                }`;

html = html.replace('                const parsedData = vis.network.convertDot(unescapedDot);', warningCode);

const appendWarningCode = `                const network = new vis.Network(container, data, options);
                window.cfgNetwork = network;
                window.cfgData = data;

                if (warnElement) {
                    container.style.position = 'relative';
                    container.appendChild(warnElement);
                }`;

html = html.replace('                const network = new vis.Network(container, data, options);\n                window.cfgNetwork = network;\n                window.cfgData = data;', appendWarningCode);

fs.writeFileSync('web/index.html', html);
console.log('patched cfg warning');
