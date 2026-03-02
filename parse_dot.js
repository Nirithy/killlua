const dot = `digraph CFG {
  node [shape=box];
  subgraph cluster_0 {
    label="Function Main";
    style=dashed;
    color=gray;
    F0_BB0 [label="BB0", style=filled, fillcolor=green];
    subgraph cluster_1 {
      label="Function 1";
      style=dashed;
      color=gray;
      F1_BB0 [label="BB0", style=filled, fillcolor=green];
      F1_BB1 [label="BB1", style=filled, fillcolor=red];
    }
  }
  F1_BB0 -> F1_BB1 [label="exit"];
  F0_BB0 -> F0_BB0 [label="loop"];
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

console.log(extractDotForFunction(dot, 1));
