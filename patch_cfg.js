const fs = require('fs');
let html = fs.readFileSync('web/index.html', 'utf-8');

const oldExtract = `        function extractDotForFunction(dotStr, functionId) {
            if (functionId === "-1" || functionId === -1) return dotStr;
            const prefix = \`F\${functionId}_BB\`;
            const lines = dotStr.split('\\n');
            let out = ['digraph CFG {', '  node [shape=box];'];
            for (let line of lines) {
                line = line.trim();
                if (line.startsWith(prefix)) out.push('  ' + line);
            }
            out.push('}');
            return out.join('\\n');
        }`;

const newExtract = `        function extractDotForFunction(dotStr, functionId) {
            if (functionId === "-1" || functionId === -1 || functionId === "All") return dotStr;
            const prefix = \`F\${functionId}_BB\`;
            const lines = dotStr.split('\\n');
            let out = ['digraph CFG {', '  node [shape=box];'];
            let inTargetSubgraph = false;

            for (let line of lines) {
                let trimmed = line.trim();
                if (trimmed.startsWith(\`subgraph cluster_\${functionId} {\`)) {
                    inTargetSubgraph = true;
                    out.push(line);
                    continue;
                }
                if (inTargetSubgraph && trimmed === '}') {
                    inTargetSubgraph = false;
                    out.push(line);
                    continue;
                }
                if (inTargetSubgraph) {
                    out.push(line);
                    continue;
                }
                // Match edges
                if (trimmed.startsWith(prefix) && trimmed.includes('->')) {
                    out.push('  ' + trimmed);
                }
            }
            out.push('}');
            return out.join('\\n');
        }`;

if (html.includes(oldExtract)) {
    html = html.replace(oldExtract, newExtract);
    fs.writeFileSync('web/index.html', html);
    console.log('Patched CFG extraction successfully');
} else {
    console.log('Could not find the target code to patch');
}
