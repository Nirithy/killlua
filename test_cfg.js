const dotStr = `digraph CFG {
  node [shape=box];
  subgraph cluster_0 {
    label="Function Main";
    F0_BB0 [label="BB0 [PC 0-5]\n0: MOVE v0 v1"];
    F0_BB1 [label="BB1 [PC 6-10]"];
  }
  subgraph cluster_1 {
    label="Function 1";
    F1_BB0 [label="BB0 [PC 0-5]"];
  }
  F0_BB0 -> F0_BB1 [label="T"];
  F1_BB0 -> F1_BB0 [label="loop"];
}`;

function extractDotForFunction(dotStr, functionId) {
    if (functionId === "-1" || functionId === -1) return dotStr;
    const prefix = `F${functionId}_BB`;
    const lines = dotStr.split('\n');
    let out = ['digraph CFG {', '  node [shape=box];'];
    for (let line of lines) {
        line = line.trim();
        if (line.startsWith(prefix)) out.push('  ' + line);
    }
    out.push('}');
    return out.join('\n');
}

console.log(extractDotForFunction(dotStr, "1"));
console.log("-----");
console.log(extractDotForFunction(dotStr, 0));
