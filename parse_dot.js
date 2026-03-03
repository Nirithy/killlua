const dotStr = `digraph CFG {
  node [shape=box];
  subgraph cluster_0 {
    label="Function Main";
    style=dashed;
    color=gray;
    F0_BB0 [label="BB0 [PC 0-5]\n0: MOVE v0 v1"];
    F0_BB1 [label="BB1 [PC 6-10]"];
  }
  subgraph cluster_1 {
    label="Function 1";
    style=dashed;
    color=gray;
    F1_BB0 [label="BB0 [PC 0-5]"];
  }
  F0_BB0 -> F0_BB1 [label="T", color="#228B22"];
  F1_BB0 -> F1_BB0 [label="loop", style=dashed, color="#4169E1"];
}`;

function extractDotForFunction(dotStr, functionId) {
    if (functionId === "-1" || functionId === -1 || functionId === "All") return dotStr;
    const prefix = `F${functionId}_BB`;
    const lines = dotStr.split('\n');
    let out = ['digraph CFG {', '  node [shape=box];'];

    let inTargetSubgraph = false;

    for (let line of lines) {
        let trimmed = line.trim();

        // Check for subgraph start
        if (trimmed.startsWith(`subgraph cluster_${functionId} {`)) {
            inTargetSubgraph = true;
            out.push(line);
            continue;
        }

        // Check for subgraph end
        if (inTargetSubgraph && trimmed === '}') {
            inTargetSubgraph = false;
            out.push(line);
            continue;
        }

        // Add content if we're inside the target subgraph
        if (inTargetSubgraph) {
            out.push(line);
            continue;
        }

        // Check for edges
        if (trimmed.startsWith(prefix) && trimmed.includes('->')) {
            out.push('  ' + trimmed);
        }
    }

    out.push('}');
    return out.join('\n');
}

console.log(extractDotForFunction(dotStr, "1"));
console.log("-----");
console.log(extractDotForFunction(dotStr, "0"));
