const fs = require('fs');
let html = fs.readFileSync('web/index.html', 'utf-8');

const pseudoFuncSearch = `        function updateAnalysisPseudoCode(funcId) {`;
const pseudoFuncEndSearch = `            container.innerText = pseudo || "No instructions found.";
        }`;

const idxStart = html.indexOf(pseudoFuncSearch);
const idxEnd = html.indexOf(pseudoFuncEndSearch, idxStart) + pseudoFuncEndSearch.length;

if (idxStart !== -1 && idxEnd !== -1) {
    const newPseudoFunc = `        function updateAnalysisPseudoCode(funcId) {
            const container = document.getElementById('pseudoCodeOutput');
            if (!container) return;
            const text = document.getElementById('optimizedDisasm').innerText;
            if (!text || text.trim() === '' || text.includes('暂无数据')) {
                container.innerText = '暂无反汇编数据。';
                return;
            }

            const lines = text.split('\\n');
            let funcLines = [];
            let inFunc = false;
            let targetIdStr = \`F\${funcId}\`;
            if (funcId === "0" || funcId === 0) targetIdStr = 'Main';

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                if (targetIdStr === 'Main') {
                    if (line.trim().startsWith('; ') && i < 5 && text.includes('; --[=========[')) {
                        if (line.includes('upvalues, ') && line.includes('locals, ')) {
                            inFunc = true;
                            continue;
                        }
                    }
                    if (inFunc && line.trim().startsWith('.func F')) {
                        inFunc = false;
                        break;
                    }
                } else {
                    if (line.trim().startsWith(\`.func \${targetIdStr} \`)) {
                        inFunc = true;
                        continue;
                    }
                    if (inFunc && line.trim().startsWith(\`.end ; \${targetIdStr}\`)) {
                        inFunc = false;
                        break;
                    }
                }

                if (inFunc && !line.trim().startsWith(';') && !line.trim().startsWith('.func') && !line.trim().startsWith('.end') && !line.trim().startsWith('.source') && !line.trim().startsWith('.linedefined') && !line.trim().startsWith('.lastlinedefined') && !line.trim().startsWith('.numparams') && !line.trim().startsWith('.is_vararg') && !line.trim().startsWith('.maxstacksize')) {
                    funcLines.push(line);
                }
            }

            let pseudo = "";
            let indent = "";
            for (let line of funcLines) {
                const trimmed = line.trim();
                if (!trimmed) continue;

                if (trimmed.startsWith(':goto_')) {
                    pseudo += \`\\n\${indent.slice(0, Math.max(0, indent.length - 2))}\${trimmed}\\n\`;
                    continue;
                }

                if (trimmed.startsWith('.local')) {
                    const match = trimmed.match(/\\.local\\s+(v\\d+)\\s+"(.*?)"/);
                    if (match) {
                        pseudo += \`\${indent}local \${match[2]} /* \${match[1]} */\\n\`;
                    } else {
                        pseudo += \`\${indent}// \${trimmed}\\n\`;
                    }
                    continue;
                }

                if (trimmed.startsWith('.upval')) {
                    const match = trimmed.match(/\\.upval\\s+(.)\\d+\\s+"(.*?)"\\s*;\\s*(u\\d+)/);
                    if (match) {
                        pseudo += \`\${indent}// upval \${match[2]} /* \${match[3]} */\\n\`;
                    } else {
                        pseudo += \`\${indent}// \${trimmed}\\n\`;
                    }
                    continue;
                }

                if (trimmed.startsWith('.line')) {
                    continue; // Skip line numbers for cleaner pseudo
                }

                const parts = trimmed.split(/\\s+/);
                const op = parts[0];

                let stmt = line;

                if (op === 'MOVE' && parts.length >= 3) {
                    stmt = \`\${parts[1]} = \${parts[2]}\`;
                } else if (op === 'LOADK' && parts.length >= 3) {
                    stmt = \`\${parts[1]} = \${parts.slice(2).join(' ')}\`;
                } else if (op === 'LOADBOOL' && parts.length >= 4) {
                    stmt = \`\${parts[1]} = \${parts[2] !== '0' ? 'true' : 'false'}\`;
                    if (parts[3] !== '0') stmt += \` // skip next instruction\`;
                } else if (op === 'LOADNIL' && parts.length >= 2) {
                    let vars = parts[1].split('..');
                    if (vars.length > 1) {
                        let start = parseInt(vars[0].substring(1));
                        let end = parseInt(vars[1].substring(1));
                        let vList = [];
                        for(let v=start; v<=end; v++) vList.push('v'+v);
                        stmt = \`\${vList.join(', ')} = nil\`;
                    } else {
                        stmt = \`\${parts[1]} = nil\`;
                    }
                } else if (op === 'GETUPVAL' && parts.length >= 3) {
                    stmt = \`\${parts[1]} = \${parts[2]}\`;
                } else if (op === 'GETTABUP' && parts.length >= 4) {
                    let key = parts[3];
                    if (key.startsWith('"') && key.endsWith('"') && /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key.slice(1, -1))) {
                        stmt = \`\${parts[1]} = \${parts[2]}.\${key.slice(1, -1)}\`;
                    } else {
                        stmt = \`\${parts[1]} = \${parts[2]}[\${key}]\`;
                    }
                } else if (op === 'GETTABLE' && parts.length >= 4) {
                    let key = parts[3];
                    if (key.startsWith('"') && key.endsWith('"') && /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key.slice(1, -1))) {
                        stmt = \`\${parts[1]} = \${parts[2]}.\${key.slice(1, -1)}\`;
                    } else {
                        stmt = \`\${parts[1]} = \${parts[2]}[\${key}]\`;
                    }
                } else if (op === 'SETTABUP' && parts.length >= 4) {
                    let key = parts[2];
                    if (key.startsWith('"') && key.endsWith('"') && /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key.slice(1, -1))) {
                        stmt = \`\${parts[1]}.\${key.slice(1, -1)} = \${parts[3]}\`;
                    } else {
                        stmt = \`\${parts[1]}[\${key}] = \${parts[3]}\`;
                    }
                } else if (op === 'SETUPVAL' && parts.length >= 3) {
                    stmt = \`\${parts[2]} = \${parts[1]}\`;
                } else if (op === 'SETTABLE' && parts.length >= 4) {
                    let key = parts[2];
                    if (key.startsWith('"') && key.endsWith('"') && /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key.slice(1, -1))) {
                        stmt = \`\${parts[1]}.\${key.slice(1, -1)} = \${parts[3]}\`;
                    } else {
                        stmt = \`\${parts[1]}[\${key}] = \${parts[3]}\`;
                    }
                } else if (op === 'NEWTABLE' && parts.length >= 4) {
                    stmt = \`\${parts[1]} = {}\`;
                } else if (op === 'SELF' && parts.length >= 4) {
                    let key = parts[3];
                    let r1 = parseInt(parts[1].substring(1));
                    let r2 = r1 + 1;
                    if (key.startsWith('"') && key.endsWith('"') && /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key.slice(1, -1))) {
                        stmt = \`v\${r2} = \${parts[2]}; \${parts[1]} = \${parts[2]}:\${key.slice(1, -1)}\`;
                    } else {
                        stmt = \`v\${r2} = \${parts[2]}; \${parts[1]} = \${parts[2]}[\${key}] /* self */\`;
                    }
                } else if (['ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'POW', 'IDIV', 'BAND', 'BOR', 'BXOR', 'SHL', 'SHR'].includes(op) && parts.length >= 4) {
                    const symMap = {'ADD':'+', 'SUB':'-', 'MUL':'*', 'DIV':'/', 'MOD':'%', 'POW':'^', 'IDIV':'//', 'BAND':'&', 'BOR':'|', 'BXOR':'~', 'SHL':'<<', 'SHR':'>>'};
                    stmt = \`\${parts[1]} = \${parts[2]} \${symMap[op]} \${parts[3]}\`;
                } else if (['UNM', 'BNOT', 'NOT', 'LEN'].includes(op) && parts.length >= 3) {
                    const symMap = {'UNM':'-', 'BNOT':'~', 'NOT':'not ', 'LEN':'#'};
                    stmt = \`\${parts[1]} = \${symMap[op]}\${parts[2]}\`;
                } else if (op === 'CONCAT' && parts.length >= 4) {
                    let rB = parseInt(parts[2].substring(1));
                    let rC = parseInt(parts[3].substring(1));
                    let concatVars = [];
                    for(let v = rB; v <= rC; v++) concatVars.push('v'+v);
                    stmt = \`\${parts[1]} = \${concatVars.join(' .. ')}\`;
                } else if (op === 'JMP' && parts.length >= 2) {
                    stmt = \`goto \${parts[parts.length-1]}\`;
                } else if (['EQ', 'LT', 'LE', 'NEQ', 'GE', 'GT'].includes(op) && parts.length >= 4) {
                    const symMap = {'EQ':'==', 'LT':'<', 'LE':'<=', 'NEQ':'~=', 'GE':'>=', 'GT':'>'};
                    let isTrue = parts[1] !== '0';
                    stmt = \`if (\${parts[2]} \${symMap[op]} \${parts[3]}) \${isTrue ? '==' : '~='} true then\`;
                } else if (op === 'TEST' && parts.length >= 3) {
                    stmt = \`if \${parts[2] === '0' ? '' : 'not '}\${parts[1]} then\`;
                } else if (op === 'TESTSET' && parts.length >= 4) {
                    stmt = \`if \${parts[3] === '0' ? 'not ' : ''}\${parts[2]} then \${parts[1]} = \${parts[2]}\`;
                } else if (op === 'CALL' && parts.length >= 3) {
                    let retStr = "";
                    let argStr = "";

                    let callStr = parts[1];
                    let args = parts[2];
                    let rets = parts[3];

                    // parse args
                    if (args) {
                        if (args.includes('..')) {
                            let rng = args.split('..');
                            let start = parseInt(rng[0].substring(1));
                            let end = parseInt(rng[1].substring(1));
                            let aList = [];
                            for(let v=start+1; v<=end; v++) aList.push('v'+v);
                            argStr = aList.join(', ');
                        } else if (args !== callStr) {
                            argStr = "..."; // Should handle better theoretically but simplifies for now
                        }
                    }

                    // parse rets
                    if (rets) {
                        if (rets.includes('..')) {
                            let rng = rets.split('..');
                            let start = parseInt(rng[0].substring(1));
                            let end = parseInt(rng[1].substring(1));
                            let rList = [];
                            for(let v=start; v<=end; v++) rList.push('v'+v);
                            retStr = rList.join(', ') + " = ";
                        } else {
                            retStr = rets + " = ";
                        }
                    } else if (parts.length === 3 && parts[2] === 'v'+(parseInt(parts[1].substring(1)))) {
                        // 0 args, 0 rets implied often in some asm syntax variants
                    } else {
                        // Var rets
                        retStr = \`\${parts[1]}... = \`;
                    }

                    stmt = \`\${retStr}\${parts[1]}(\${argStr})\`;
                } else if (op === 'TAILCALL' && parts.length >= 3) {
                    let argStr = "";
                    let callStr = parts[1];
                    let args = parts[2];
                    if (args && args.includes('..')) {
                        let rng = args.split('..');
                        let start = parseInt(rng[0].substring(1));
                        let end = parseInt(rng[1].substring(1));
                        let aList = [];
                        for(let v=start+1; v<=end; v++) aList.push('v'+v);
                        argStr = aList.join(', ');
                    }
                    stmt = \`return \${parts[1]}(\${argStr})\`;
                } else if (op === 'RETURN') {
                    if (parts.length > 1) {
                        let retVars = parts.slice(1).join(' ');
                        if (retVars.includes('..')) {
                            let rng = retVars.split('..');
                            let start = parseInt(rng[0].substring(1));
                            let end = parseInt(rng[1].substring(1));
                            let rList = [];
                            for(let v=start; v<=end; v++) rList.push('v'+v);
                            stmt = \`return \${rList.join(', ')}\`;
                        } else {
                            stmt = \`return \${retVars}\`;
                        }
                    } else {
                        stmt = \`return\`;
                    }
                } else if (op === 'CLOSURE' && parts.length >= 3) {
                    stmt = \`\${parts[1]} = function() -- \${parts[2]}\`;
                } else if (op === 'FORPREP' && parts.length >= 3) {
                    stmt = \`// for loop init, goto \${parts[parts.length-1]}\\n\${indent}for \${parts[1]} = \${parts[1]}, \${parts[1]}+1, \${parts[1]}+2 do\`;
                    indent += "  ";
                } else if (op === 'FORLOOP' && parts.length >= 3) {
                    indent = indent.slice(0, Math.max(0, indent.length - 2));
                    stmt = \`end // goto \${parts[parts.length-1]}\`;
                } else if (op === 'TFORCALL' && parts.length >= 4) {
                    stmt = \`// tforcall \${parts[1]}\`;
                } else if (op === 'TFORLOOP' && parts.length >= 3) {
                    stmt = \`// tforloop, goto \${parts[parts.length-1]}\`;
                }

                pseudo += \`\${indent}  \${stmt}\\n\`;
            }

            container.innerText = pseudo || "No instructions found.";
        }`;

    html = html.substring(0, idxStart) + newPseudoFunc + html.substring(idxEnd);
    fs.writeFileSync('web/index.html', html);
    console.log("Patched updateAnalysisPseudoCode");
} else {
    console.log("Could not find updateAnalysisPseudoCode bounds");
}
