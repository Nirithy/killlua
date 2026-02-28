"""
Control Flow Graph (CFG) Builder for Lua Bytecode

Builds a directed graph representing the control flow of Lua bytecode.
Uses networkx for graph representation and analysis.
"""

from typing import List, Dict, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum, auto
import networkx as nx

from .parser import Prototype, Instruction
from .opcodes import Opcode, OpMode, get_opcode_info


class EdgeType(Enum):
    """
    Types of control flow edges.
    
    For conditional instructions (EQ, LT, LE, TEST, TESTSET, etc.):
    
    Lua VM semantics: `if (condition != A/C) then pc++` (skip next instruction)
    
    Example for `if x == y then ... else ... end` compiled as:
      EQ 0 x y      ; A=0, so skip if (x==y) is TRUE (since true != 0)
      JMP to_else   ; this JMP is skipped when x==y, executed when x!=y
      ... then ...  ; reached when x==y (skipped JMP)
    to_else:
      ... else ...  ; reached when x!=y (executed JMP)
    
    Edge semantics (from the conditional instruction's perspective):
    
    - COND_TRUE:  Skip path - condition caused pc++ (skipped next instruction)
                  For EQ 0: comparison was TRUE, so (TRUE != 0) caused skip
                  Goes to pc+2, typically the "then" block
                  
    - COND_FALSE: No-skip path - condition did NOT cause pc++
                  For EQ 0: comparison was FALSE, so (FALSE != 0) is false, no skip
                  Executes next instruction (usually JMP), goes to "else" block
    
    Summary: COND_TRUE = "then" branch, COND_FALSE = "else" branch
    """
    SEQUENTIAL = auto()    # Normal sequential flow
    JUMP = auto()          # Unconditional jump
    COND_TRUE = auto()     # Conditional branch - skip path (condition caused pc++)
    COND_FALSE = auto()    # Conditional branch - no-skip path (next instr executed)
    LOOP_BACK = auto()     # Loop back edge
    LOOP_EXIT = auto()     # Loop exit edge
    CALL = auto()          # Function call (internal)
    RETURN = auto()        # Return from function


@dataclass
class BasicBlock:
    """A basic block in the CFG"""
    id: int
    start_pc: int
    end_pc: int  # Exclusive
    instructions: List[Instruction] = field(default_factory=list)
    is_entry: bool = False
    is_exit: bool = False
    predecessors: Set[int] = field(default_factory=set)
    successors: Set[int] = field(default_factory=set)
    
    @property
    def size(self) -> int:
        return self.end_pc - self.start_pc
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if isinstance(other, BasicBlock):
            return self.id == other.id
        return False


@dataclass
class CFGEdge:
    """An edge in the CFG"""
    source: int  # Basic block ID
    target: int  # Basic block ID
    edge_type: EdgeType
    condition: Optional[str] = None  # For conditional edges


class CFGBuilder:
    """Builds a Control Flow Graph from Lua bytecode"""
    
    # Opcodes that terminate a basic block
    TERMINATOR_OPCODES = {
        Opcode.JMP,      # Unconditional jump
        Opcode.EQ,       # Comparison (followed by JMP)
        Opcode.LT,
        Opcode.LE,
        Opcode.NEQ,
        Opcode.GE,
        Opcode.GT,
        Opcode.TEST,     # Test and skip
        Opcode.TESTSET,
        Opcode.RETURN,   # Return
        Opcode.TAILCALL, # Tail call (implicit return)
        Opcode.FORLOOP,  # For loop
        Opcode.FORPREP,  # For loop preparation
        Opcode.TFORLOOP, # Generic for loop
        # Note: LOADBOOL is NOT a terminator - only LOADBOOL with C!=0 skips next instruction
        # and it's handled specially in _find_leaders and _create_edges
    }
    
    # Opcodes that are jump targets
    JUMP_OPCODES = {
        Opcode.JMP,
        Opcode.FORLOOP,
        Opcode.FORPREP,
        Opcode.TFORLOOP,
    }
    
    def __init__(self, proto: Prototype):
        self.proto = proto
        self.instructions = proto.code
        self.graph = nx.DiGraph()
        self.blocks: Dict[int, BasicBlock] = {}  # block_id -> BasicBlock
        self.pc_to_block: Dict[int, int] = {}    # pc -> block_id
        self.block_counter = 0
    
    def build(self) -> nx.DiGraph:
        """Build the CFG"""
        if not self.instructions:
            return self.graph
        
        # Step 1: Find all block leaders (start of basic blocks)
        leaders = self._find_leaders()
        
        # Step 2: Create basic blocks
        self._create_blocks(leaders)
        
        # Step 3: Add edges between blocks
        self._create_edges()
        
        # Step 4: Mark entry and exit blocks
        self._mark_special_blocks()
        
        return self.graph
    
    def _find_leaders(self) -> Set[int]:
        """Find all basic block leaders (first instruction of each block)"""
        leaders = {0}  # First instruction is always a leader
        
        for pc, instr in enumerate(self.instructions):
            opcode = instr.opcode
            
            # Jump targets are leaders
            if opcode in self.JUMP_OPCODES:
                target = pc + instr.sbx + 1
                if 0 <= target < len(self.instructions):
                    leaders.add(target)
            
            # Comparison / test opcodes: the instruction after the comparison AND
            # the instruction after the following JMP (pc+2) are leaders
            if opcode in (Opcode.EQ, Opcode.LT, Opcode.LE, Opcode.NEQ, 
                         Opcode.GE, Opcode.GT, Opcode.TEST, Opcode.TESTSET):
                # The next instruction (pc+1) starts a block
                if pc + 1 < len(self.instructions):
                    leaders.add(pc + 1)
                # The skip target (pc+2) is also a leader, regardless of what pc+1 is
                # This is important for obfuscated code where pc+1 may not be JMP
                if pc + 2 < len(self.instructions):
                    leaders.add(pc + 2)
            
            # LOADBOOL with C != 0 can skip next instruction
            if opcode == Opcode.LOADBOOL and instr.c != 0:
                if pc + 2 < len(self.instructions):
                    leaders.add(pc + 2)
                # Also make pc+1 a leader since the block ends here
                if pc + 1 < len(self.instructions):
                    leaders.add(pc + 1)
            
            # SETLIST with C == 0: next instruction is EXTRAARG (data, not executable)
            # The real next instruction is at pc+2
            # Make pc+1 a leader so SETLIST ends its block, and pc+2 starts a new one
            if opcode == Opcode.SETLIST and instr.c == 0:
                if pc + 1 < len(self.instructions):
                    leaders.add(pc + 1)  # EXTRAARG forms its own "block" (will be skipped)
                if pc + 2 < len(self.instructions):
                    leaders.add(pc + 2)  # Real next instruction
            
            # LOADKX: next instruction is EXTRAARG containing the constant index
            # Similar to SETLIST with C=0
            if opcode == Opcode.LOADKX:
                if pc + 1 < len(self.instructions):
                    leaders.add(pc + 1)
                if pc + 2 < len(self.instructions):
                    leaders.add(pc + 2)
            
            # Instruction after terminator is a leader (for fallthrough)
            if opcode in self.TERMINATOR_OPCODES:
                if pc + 1 < len(self.instructions):
                    leaders.add(pc + 1)
            
            # Instruction after RETURN or TAILCALL - next block
            if opcode in (Opcode.RETURN, Opcode.TAILCALL):
                if pc + 1 < len(self.instructions):
                    leaders.add(pc + 1)
        
        return leaders
    
    def _create_blocks(self, leaders: Set[int]):
        """Create basic blocks from leaders"""
        sorted_leaders = sorted(leaders)
        
        for i, start_pc in enumerate(sorted_leaders):
            # End PC is the start of next block, or end of instructions
            if i + 1 < len(sorted_leaders):
                end_pc = sorted_leaders[i + 1]
            else:
                end_pc = len(self.instructions)
            
            block = BasicBlock(
                id=self.block_counter,
                start_pc=start_pc,
                end_pc=end_pc,
                instructions=self.instructions[start_pc:end_pc]
            )
            
            self.blocks[block.id] = block
            self.graph.add_node(block.id, block=block)
            
            # Map each PC to its block
            for pc in range(start_pc, end_pc):
                self.pc_to_block[pc] = block.id
            
            self.block_counter += 1
    
    def _create_edges(self):
        """Create edges between basic blocks"""
        for block_id, block in self.blocks.items():
            if not block.instructions:
                continue
            
            last_instr = block.instructions[-1]
            last_pc = block.end_pc - 1
            
            opcode = last_instr.opcode
            
            # Handle different terminator types
            if opcode == Opcode.JMP:
                # Unconditional jump
                target_pc = last_pc + last_instr.sbx + 1
                self._add_edge(block_id, target_pc, EdgeType.JUMP)
            
            elif opcode in (Opcode.EQ, Opcode.LT, Opcode.LE, Opcode.NEQ,
                          Opcode.GE, Opcode.GT):
                # LuaClosure.java case 24-26 (EQ, LT, LE):
                #   if (RK(B).op(RK(C)) != A) { pc++; }  // skip next instruction
                #
                # Edge semantics:
                # - COND_TRUE:  skip path (cmp_result != A), typically goes to "then" branch
                # - COND_FALSE: no-skip path (cmp_result == A), falls through to next instruction
                #
                # Note: When followed by JMP, COND_FALSE goes to the JMP block (not directly
                # to JMP's target). The JMP block will then add its own edge to the target.
                # This ensures the JMP block has an incoming edge and won't be incorrectly
                # identified as unreachable dead code.
                next_pc = last_pc + 1
                skip_pc = last_pc + 2
                if next_pc < len(self.instructions):
                    next_instr = self.instructions[next_pc]
                    if next_instr.opcode == Opcode.JMP:
                        # Common pattern: comparison followed by JMP
                        # Skip (cmp != A): skip the JMP, continue to pc+2
                        if skip_pc < len(self.instructions):
                            self._add_edge(block_id, skip_pc, EdgeType.COND_TRUE)
                        # No skip (cmp == A): fall through to JMP instruction
                        # (JMP block will add edge to its target)
                        self._add_edge(block_id, next_pc, EdgeType.COND_FALSE)
                    else:
                        # Non-standard: no following JMP (possible in obfuscated code)
                        # No skip: execute next instruction (pc+1)
                        self._add_edge(block_id, next_pc, EdgeType.COND_FALSE)
                        # Skip: skip next instruction (pc+2)
                        if skip_pc < len(self.instructions):
                            self._add_edge(block_id, skip_pc, EdgeType.COND_TRUE)
            
            elif opcode in (Opcode.TEST, Opcode.TESTSET):
                # LuaClosure.java case 27-28 (TEST, TESTSET):
                #   if (toboolean(R(A/B)) != C) { pc++; }  // skip next instruction
                #
                # Edge semantics:
                # - COND_TRUE:  skip path (bool != C), typically goes to "then" branch
                # - COND_FALSE: no-skip path (bool == C), falls through to next instruction
                #
                # Note: When followed by JMP, COND_FALSE goes to the JMP block (not directly
                # to JMP's target). The JMP block will then add its own edge to the target.
                # This ensures the JMP block has an incoming edge and won't be incorrectly
                # identified as unreachable dead code.
                next_pc = last_pc + 1
                skip_pc = last_pc + 2
                if next_pc < len(self.instructions):
                    next_instr = self.instructions[next_pc]
                    if next_instr.opcode == Opcode.JMP:
                        # Common pattern: TEST/TESTSET followed by JMP
                        # Skip (bool != C): skip the JMP, continue to pc+2
                        if skip_pc < len(self.instructions):
                            self._add_edge(block_id, skip_pc, EdgeType.COND_TRUE)
                        # No skip (bool == C): fall through to JMP instruction
                        # (JMP block will add edge to its target)
                        self._add_edge(block_id, next_pc, EdgeType.COND_FALSE)
                    else:
                        # Non-standard: no following JMP (possible in obfuscated code)
                        # Skip (bool != C): go to pc+2
                        if skip_pc < len(self.instructions):
                            self._add_edge(block_id, skip_pc, EdgeType.COND_TRUE)
                        # No skip (bool == C): execute next instruction (pc+1)
                        self._add_edge(block_id, next_pc, EdgeType.COND_FALSE)
            
            elif opcode == Opcode.FORLOOP:
                # LuaClosure.java case 32:
                #   R(A) += R(A+2)  // increment counter
                #   if R(A) <?= R(A+1) then  // still within limit
                #       pc += sbx; R(A+3) = R(A)  // jump back to loop body
                #   else
                #       fall through (exit loop)
                #
                # Edges:
                # - LOOP_BACK: jump back when loop continues
                # - LOOP_EXIT: fall through when loop ends
                target_pc = last_pc + last_instr.sbx + 1
                self._add_edge(block_id, target_pc, EdgeType.LOOP_BACK)
                # Loop exit (fallthrough)
                exit_pc = last_pc + 1
                if exit_pc < len(self.instructions):
                    self._add_edge(block_id, exit_pc, EdgeType.LOOP_EXIT)
            
            elif opcode == Opcode.FORPREP:
                # LuaClosure.java case 33:
                #   R(A) -= R(A+2)  // subtract step (will be added back on first FORLOOP)
                #   pc += sbx      // jump to FORLOOP instruction
                #
                # This is an unconditional jump to the loop test
                target_pc = last_pc + last_instr.sbx + 1
                self._add_edge(block_id, target_pc, EdgeType.JUMP)
            
            elif opcode == Opcode.TFORLOOP:
                # LuaClosure.java case 35:
                #   if R(A+1) ~= nil then
                #       R(A) = R(A+1); pc += sbx  // jump back to loop body
                #   else
                #       fall through (exit loop)
                #
                # Note: TFORCALL (case 34) precedes this and sets R(A+1)..R(A+2+C)
                target_pc = last_pc + last_instr.sbx + 1
                self._add_edge(block_id, target_pc, EdgeType.LOOP_BACK)
                # Loop exit
                exit_pc = last_pc + 1
                if exit_pc < len(self.instructions):
                    self._add_edge(block_id, exit_pc, EdgeType.LOOP_EXIT)
            
            elif opcode == Opcode.LOADBOOL and last_instr.c != 0:
                # LOADBOOL with C != 0: unconditionally skip next instruction
                # No sequential flow - this is NOT a conditional branch
                skip_pc = last_pc + 2
                if skip_pc < len(self.instructions):
                    self._add_edge(block_id, skip_pc, EdgeType.JUMP)
            
            elif opcode == Opcode.SETLIST and last_instr.c == 0:
                # SETLIST with C == 0: next instruction is EXTRAARG (data)
                # Control flow skips to pc+2
                skip_pc = last_pc + 2
                if skip_pc < len(self.instructions):
                    self._add_edge(block_id, skip_pc, EdgeType.SEQUENTIAL)
            
            elif opcode == Opcode.LOADKX:
                # LOADKX: next instruction is EXTRAARG containing the constant index
                # Control flow skips to pc+2
                skip_pc = last_pc + 2
                if skip_pc < len(self.instructions):
                    self._add_edge(block_id, skip_pc, EdgeType.SEQUENTIAL)
            
            elif opcode == Opcode.EXTRAARG:
                # EXTRAARG is data for the previous instruction, not executable code
                # It should have no outgoing edges (it's dead code in the CFG sense)
                # The only incoming edge should be from nothing (it's handled by SETLIST/LOADKX)
                pass
            
            elif opcode in (Opcode.RETURN, Opcode.TAILCALL):
                # No outgoing edges (function exit)
                pass
            
            else:
                # Sequential flow to next block
                next_pc = last_pc + 1
                if next_pc < len(self.instructions):
                    self._add_edge(block_id, next_pc, EdgeType.SEQUENTIAL)
    
    def _add_edge(self, from_block_id: int, to_pc: int, edge_type: EdgeType):
        """Add an edge from a block to the block containing the target PC"""
        if to_pc not in self.pc_to_block:
            return  # Target is outside the function
        
        to_block_id = self.pc_to_block[to_pc]
        
        # Note: Self-loops are valid (e.g., `while true do end` compiles to `JMP -1`)
        # We allow them but avoid adding duplicate edges
        if not self.graph.has_edge(from_block_id, to_block_id):
            self.graph.add_edge(from_block_id, to_block_id, edge_type=edge_type)
        
        # Always update successor/predecessor sets (handles self-loops correctly)
        self.blocks[from_block_id].successors.add(to_block_id)
        self.blocks[to_block_id].predecessors.add(from_block_id)
    
    def _mark_special_blocks(self):
        """Mark entry and exit blocks"""
        # Entry block contains PC 0
        if 0 in self.pc_to_block:
            entry_id = self.pc_to_block[0]
            self.blocks[entry_id].is_entry = True
        
        # Exit blocks have no successors or end with RETURN/TAILCALL
        for block_id, block in self.blocks.items():
            if not block.successors:
                block.is_exit = True
            elif block.instructions:
                last_opcode = block.instructions[-1].opcode
                if last_opcode in (Opcode.RETURN, Opcode.TAILCALL):
                    block.is_exit = True
    
    def get_block(self, block_id: int) -> Optional[BasicBlock]:
        """Get a basic block by ID"""
        return self.blocks.get(block_id)
    
    def get_block_at_pc(self, pc: int) -> Optional[BasicBlock]:
        """Get the basic block containing the given PC"""
        block_id = self.pc_to_block.get(pc)
        if block_id is not None:
            return self.blocks[block_id]
        return None
    
    def get_entry_block(self) -> Optional[BasicBlock]:
        """Get the entry block"""
        for block in self.blocks.values():
            if block.is_entry:
                return block
        return None
    
    def get_exit_blocks(self) -> List[BasicBlock]:
        """Get all exit blocks"""
        return [block for block in self.blocks.values() if block.is_exit]
    
    def get_predecessors(self, block_id: int) -> List[BasicBlock]:
        """Get predecessor blocks"""
        return [self.blocks[pred] for pred in self.graph.predecessors(block_id)]
    
    def get_successors(self, block_id: int) -> List[BasicBlock]:
        """Get successor blocks"""
        return [self.blocks[succ] for succ in self.graph.successors(block_id)]


class CFG:
    """High-level CFG representation with analysis capabilities"""
    
    def __init__(self, proto: Prototype):
        self.proto = proto
        self.builder = CFGBuilder(proto)
        self.graph = self.builder.build()
        self.blocks = self.builder.blocks
        self.pc_to_block = self.builder.pc_to_block
    
    @property
    def entry_block(self) -> Optional[BasicBlock]:
        return self.builder.get_entry_block()
    
    @property
    def exit_blocks(self) -> List[BasicBlock]:
        return self.builder.get_exit_blocks()
    
    def get_block(self, block_id: int) -> Optional[BasicBlock]:
        return self.blocks.get(block_id)
    
    def get_block_at_pc(self, pc: int) -> Optional[BasicBlock]:
        block_id = self.pc_to_block.get(pc)
        return self.blocks.get(block_id) if block_id is not None else None
    
    def dominators(self) -> Dict[int, Set[int]]:
        """Compute dominators for each block"""
        if not self.entry_block:
            return {}
        
        entry_id = self.entry_block.id
        
        # Initialize: entry dominates only itself, all others dominated by all
        all_blocks = set(self.blocks.keys())
        dom = {bid: all_blocks.copy() for bid in self.blocks}
        dom[entry_id] = {entry_id}
        
        # Iterate until fixed point
        changed = True
        while changed:
            changed = False
            for block_id in self.blocks:
                if block_id == entry_id:
                    continue
                
                preds = list(self.graph.predecessors(block_id))
                if not preds:
                    continue
                
                # Dom(n) = {n} ∪ (∩ Dom(p) for p in predecessors)
                new_dom = all_blocks.copy()
                for pred in preds:
                    new_dom &= dom[pred]
                new_dom.add(block_id)
                
                if new_dom != dom[block_id]:
                    dom[block_id] = new_dom
                    changed = True
        
        return dom
    
    def immediate_dominators(self) -> Dict[int, Optional[int]]:
        """Compute immediate dominators"""
        dom = self.dominators()
        idom = {}
        
        for block_id in self.blocks:
            # idom(n) is the closest strict dominator
            strict_doms = dom[block_id] - {block_id}
            if not strict_doms:
                idom[block_id] = None
                continue
            
            # Find the dominator that is dominated by all other strict dominators
            for candidate in strict_doms:
                if all(candidate in dom[other] for other in strict_doms if other != candidate):
                    idom[block_id] = candidate
                    break
            else:
                idom[block_id] = None
        
        return idom
    
    def find_loops(self) -> List[Tuple[int, Set[int]]]:
        """Find natural loops (header, body blocks)"""
        loops = []
        
        # A natural loop has a back edge n -> h where h dominates n
        dom = self.dominators()
        
        for edge in self.graph.edges():
            tail, head = edge
            if head in dom[tail]:  # Back edge found
                # Collect all nodes in the loop
                loop_body = {head, tail}
                worklist = [tail]
                
                while worklist:
                    node = worklist.pop()
                    for pred in self.graph.predecessors(node):
                        if pred not in loop_body:
                            loop_body.add(pred)
                            worklist.append(pred)
                
                loops.append((head, loop_body))
        
        return loops
    
    def find_unreachable_blocks(self) -> Set[int]:
        """Find blocks unreachable from entry"""
        if not self.entry_block:
            return set(self.blocks.keys())
        
        reachable = set()
        worklist = [self.entry_block.id]
        
        while worklist:
            block_id = worklist.pop()
            if block_id in reachable:
                continue
            reachable.add(block_id)
            
            for succ in self.graph.successors(block_id):
                if succ not in reachable:
                    worklist.append(succ)
        
        return set(self.blocks.keys()) - reachable
    
    def to_dot(self, include_instructions: bool = True) -> str:
        """Generate DOT graph representation for visualization"""
        lines = ["digraph CFG {"]
        lines.append("  rankdir=TB;")
        lines.append("  node [shape=box, fontname=\"Courier\"];")
        lines.append("  edge [fontname=\"Courier\"];")
        
        for block_id, block in self.blocks.items():
            label_parts = [f"BB{block_id} [PC {block.start_pc}-{block.end_pc-1}]"]
            
            if include_instructions:
                for i, instr in enumerate(block.instructions):
                    pc = block.start_pc + i
                    label_parts.append(f"{pc}: {instr.opcode_name}")
            
            label = "\\n".join(label_parts)
            
            attrs = [f'label="{label}"']
            if block.is_entry:
                attrs.append('style=filled')
                attrs.append('fillcolor="#90EE90"')  # lightgreen
            elif block.is_exit:
                attrs.append('style=filled')
                attrs.append('fillcolor="#F08080"')  # lightcoral
            
            lines.append(f'  {block_id} [{", ".join(attrs)}];')
        
        # Edges
        for edge in self.graph.edges(data=True):
            src, dst, data = edge
            edge_type = data.get('edge_type', EdgeType.SEQUENTIAL)
            
            attrs = []
            if edge_type == EdgeType.COND_TRUE:
                attrs.append('label="T"')
                attrs.append('color="#228B22"')  # forestgreen
            elif edge_type == EdgeType.COND_FALSE:
                attrs.append('label="F"')
                attrs.append('color="#DC143C"')  # crimson
            elif edge_type == EdgeType.LOOP_BACK:
                attrs.append('style=dashed')
                attrs.append('color="#4169E1"')  # royalblue
            elif edge_type == EdgeType.LOOP_EXIT:
                attrs.append('label="exit"')
            
            attr_str = f' [{", ".join(attrs)}]' if attrs else ''
            lines.append(f'  {src} -> {dst}{attr_str};')
        
        lines.append("}")
        return "\n".join(lines)
    
    def save_dot(self, filepath: str, include_instructions: bool = True):
        """Save DOT representation to file"""
        with open(filepath, 'w') as f:
            f.write(self.to_dot(include_instructions))
    
    def _order_blocks(self, reachable: Set[int], strategy: str) -> List[int]:
        """
        Order blocks based on the specified strategy.
        
        Args:
            reachable: Set of reachable block IDs
            strategy: 'original', 'topological', or 'bfs'
        
        Returns:
            List of block IDs in the specified order
        """
        if strategy == 'original':
            # For 'original' strategy, we need to order blocks such that:
            # 1. For conditional blocks (EQ, LT, LE, etc.), COND_TRUE target must be at pc+2
            # 2. COND_FALSE target gets a JMP instruction at pc+1
            # 
            # We use a modified BFS that respects control flow constraints:
            # - After a conditional block, place COND_TRUE target immediately (it becomes pc+2)
            # - COND_FALSE will get an inserted JMP
            from .opcodes import Opcode
            
            ordered = []
            visited = set()
            worklist = [self.entry_block.id] if self.entry_block else []
            
            while worklist:
                block_id = worklist.pop(0)
                if block_id in visited or block_id not in reachable:
                    continue
                visited.add(block_id)
                ordered.append(block_id)
                
                block = self.blocks[block_id]
                if not block.instructions:
                    # Empty block, just add all successors
                    for succ in self.graph.successors(block_id):
                        if succ not in visited and succ in reachable:
                            worklist.append(succ)
                    continue
                
                last_instr = block.instructions[-1]
                
                # For conditional blocks, prioritize COND_TRUE (skip target) to be next
                if last_instr.opcode in (Opcode.EQ, Opcode.LT, Opcode.LE,
                                          Opcode.NEQ, Opcode.GE, Opcode.GT,
                                          Opcode.TEST, Opcode.TESTSET):
                    true_succ = None
                    false_succ = None
                    for succ_id in self.graph.successors(block_id):
                        edge_data = self.graph.edges[block_id, succ_id]
                        edge_type = edge_data.get('edge_type')
                        if edge_type == EdgeType.COND_TRUE:
                            true_succ = succ_id
                        elif edge_type == EdgeType.COND_FALSE:
                            false_succ = succ_id
                    
                    # Add COND_TRUE first (so it ends up at pc+2 after JMP insertion)
                    if true_succ is not None and true_succ not in visited and true_succ in reachable:
                        worklist.insert(0, true_succ)
                    if false_succ is not None and false_succ not in visited and false_succ in reachable:
                        # Add COND_FALSE after, it will get a JMP
                        worklist.append(false_succ)
                
                elif last_instr.opcode in (Opcode.FORLOOP, Opcode.TFORLOOP):
                    # For loops, prioritize LOOP_EXIT over LOOP_BACK
                    exit_succ = None
                    back_succ = None
                    for succ_id in self.graph.successors(block_id):
                        edge_data = self.graph.edges[block_id, succ_id]
                        edge_type = edge_data.get('edge_type')
                        if edge_type == EdgeType.LOOP_EXIT:
                            exit_succ = succ_id
                        elif edge_type == EdgeType.LOOP_BACK:
                            back_succ = succ_id
                    
                    if exit_succ is not None and exit_succ not in visited and exit_succ in reachable:
                        worklist.insert(0, exit_succ)
                    if back_succ is not None and back_succ not in visited and back_succ in reachable:
                        worklist.append(back_succ)
                
                else:
                    # Non-conditional: add successors in order
                    for succ in self.graph.successors(block_id):
                        if succ not in visited and succ in reachable:
                            worklist.append(succ)
            
            # Add any remaining reachable blocks (disconnected components)
            for bid in reachable:
                if bid not in visited:
                    ordered.append(bid)
            
            return ordered
        
        elif strategy == 'bfs':
            # BFS from entry block, prioritizing fall-through edges
            ordered = []
            visited = set()
            queue = [self.entry_block.id] if self.entry_block else []
            
            while queue:
                block_id = queue.pop(0)
                if block_id in visited or block_id not in reachable:
                    continue
                visited.add(block_id)
                ordered.append(block_id)
                
                # Get successors, prioritize non-jump edges (fall-through)
                succs = list(self.graph.successors(block_id))
                # Sort by edge type: SEQUENTIAL/COND_FALSE first, then others
                def edge_priority(succ_id):
                    if not self.graph.has_edge(block_id, succ_id):
                        return 10
                    edge_data = self.graph.edges[block_id, succ_id]
                    edge_type = edge_data.get('edge_type', EdgeType.SEQUENTIAL)
                    if edge_type in (EdgeType.SEQUENTIAL, EdgeType.COND_FALSE):
                        return 0
                    elif edge_type == EdgeType.LOOP_EXIT:
                        return 1
                    elif edge_type == EdgeType.COND_TRUE:
                        return 2
                    else:
                        return 5
                
                succs.sort(key=edge_priority)
                for succ in succs:
                    if succ not in visited and succ in reachable:
                        queue.append(succ)
            
            # Add any remaining reachable blocks (disconnected components)
            for bid in reachable:
                if bid not in visited:
                    ordered.append(bid)
            
            return ordered
        
        elif strategy == 'topological':
            # Reverse post-order DFS (topological sort respecting dominance)
            ordered = []
            visited = set()
            in_stack = set()  # For cycle detection
            
            def dfs(block_id: int):
                if block_id in visited or block_id not in reachable:
                    return
                if block_id in in_stack:
                    # Back edge (loop), skip to avoid infinite recursion
                    return
                
                in_stack.add(block_id)
                visited.add(block_id)
                
                # Visit successors, but prioritize fall-through edges
                succs = list(self.graph.successors(block_id))
                
                # Separate loop-back edges from forward edges
                forward_succs = []
                back_succs = []
                for succ in succs:
                    if succ in reachable:
                        edge_data = self.graph.edges.get((block_id, succ), {})
                        edge_type = edge_data.get('edge_type', EdgeType.SEQUENTIAL)
                        if edge_type == EdgeType.LOOP_BACK:
                            back_succs.append(succ)
                        else:
                            forward_succs.append(succ)
                
                # Sort forward successors: COND_FALSE/SEQUENTIAL first
                def edge_priority(succ_id):
                    edge_data = self.graph.edges.get((block_id, succ_id), {})
                    edge_type = edge_data.get('edge_type', EdgeType.SEQUENTIAL)
                    if edge_type in (EdgeType.SEQUENTIAL, EdgeType.COND_FALSE):
                        return 0
                    elif edge_type == EdgeType.LOOP_EXIT:
                        return 1
                    else:
                        return 2
                
                forward_succs.sort(key=edge_priority)
                
                # Visit forward successors first (they should come after current block)
                for succ in forward_succs:
                    dfs(succ)
                
                # Don't recursively visit back edges (they point to already-visited loop headers)
                
                in_stack.remove(block_id)
                ordered.append(block_id)
            
            # Start DFS from entry block
            if self.entry_block:
                dfs(self.entry_block.id)
            
            # Add any remaining reachable blocks
            for bid in reachable:
                if bid not in visited:
                    dfs(bid)
            
            # Reverse to get forward order (post-order DFS gives reverse topological)
            ordered.reverse()
            return ordered
        
        else:
            raise ValueError(f"Unknown layout strategy: {strategy}")
    
    def rebuild_code(self, layout_strategy: str = 'topological') -> List:
        """
        Rebuild the instruction list from the CFG.
        
        This method collects all instructions from reachable basic blocks in order
        and returns a new instruction list. It also updates jump targets based on
        the CFG edges (not the old instruction offsets).
        
        Args:
            layout_strategy: Block ordering strategy:
                - 'original': Sort by original start_pc (preserves original layout)
                - 'topological': Topological sort with forward edge preference
                - 'bfs': BFS from entry block (good for deobfuscated code)
        
        Returns:
            List of instructions in the new order
        """
        from .opcodes import Opcode
        from .parser import Instruction
        from copy import copy
        
        # Get all reachable blocks
        reachable = set()
        worklist = [self.entry_block.id] if self.entry_block else []
        
        while worklist:
            block_id = worklist.pop(0)
            if block_id in reachable:
                continue
            reachable.add(block_id)
            
            for succ in self.graph.successors(block_id):
                if succ not in reachable:
                    worklist.append(succ)
        
        # Order blocks based on strategy
        ordered_blocks = self._order_blocks(reachable, layout_strategy)
        
        if not ordered_blocks:
            return []
        
        # First pass: Calculate new start PC for each block, accounting for
        # potentially inserted JMP instructions after conditionals
        block_new_start = {}  # block_id -> new start PC
        block_needs_jmp = {}  # block_id -> target_block_id (if JMP needed after it)
        current_pc = 0
        
        for idx, block_id in enumerate(ordered_blocks):
            block = self.blocks[block_id]
            block_new_start[block_id] = current_pc
            current_pc += len(block.instructions)
            
            # Check if this block ends with a conditional instruction
            if block.instructions:
                last_instr = block.instructions[-1]
                if last_instr.opcode in (Opcode.EQ, Opcode.LT, Opcode.LE,
                                          Opcode.NEQ, Opcode.GE, Opcode.GT,
                                          Opcode.TEST, Opcode.TESTSET):
                    # Get the COND_FALSE (fall-through) successor from CFG
                    false_succ = None
                    for succ_id in self.graph.successors(block_id):
                        edge_data = self.graph.edges[block_id, succ_id]
                        if edge_data.get('edge_type') == EdgeType.COND_FALSE:
                            false_succ = succ_id
                            break
                    
                    if false_succ is not None and false_succ in reachable:
                        # Check if false_succ will be immediately after this block
                        next_block_id = ordered_blocks[idx + 1] if idx + 1 < len(ordered_blocks) else None
                        if next_block_id != false_succ:
                            # Need to insert a JMP to false_succ
                            block_needs_jmp[block_id] = false_succ
                            current_pc += 1
        
        # Second pass: Build the instruction list
        new_code = []
        instr_to_block = []  # new_pc -> (block_id, is_inserted_jmp, target_block_for_jmp)
        
        for block_id in ordered_blocks:
            block = self.blocks[block_id]
            
            for instr in block.instructions:
                new_code.append(copy(instr))
                instr_to_block.append((block_id, False, None))
            
            # Insert JMP if needed
            if block_id in block_needs_jmp:
                jmp_instr = Instruction.encode_new(
                    opcode=Opcode.JMP,
                    a=0,
                    sbx=0  # Will be fixed below
                )
                new_code.append(jmp_instr)
                instr_to_block.append((block_id, True, block_needs_jmp[block_id]))
        
        # Third pass: Fix all jump targets
        for new_pc, instr in enumerate(new_code):
            block_id, is_inserted, jmp_target = instr_to_block[new_pc]
            
            if is_inserted:
                # This is an inserted JMP, target is jmp_target block
                if jmp_target in block_new_start:
                    new_target = block_new_start[jmp_target]
                    new_sbx = new_target - new_pc - 1
                    instr.sbx = new_sbx
                    instr.bx = new_sbx + 131071
                    instr.raw = (instr.opcode & 0x3F) | ((instr.a & 0xFF) << 6) | ((instr.bx & 0x3FFFF) << 14)
                continue
            
            block = self.blocks[block_id]
            
            if instr.opcode == Opcode.JMP:
                # Find the JUMP successor from CFG
                target_block = None
                for succ_id in self.graph.successors(block_id):
                    edge_data = self.graph.edges[block_id, succ_id]
                    edge_type = edge_data.get('edge_type')
                    # JUMP edge OR SEQUENTIAL edge (for JMP-only blocks that were merged)
                    if edge_type == EdgeType.JUMP:
                        target_block = succ_id
                        break
                
                # If no JUMP edge found, try any edge (fallback for edge redirection cases)
                if target_block is None:
                    succs = list(self.graph.successors(block_id))
                    if len(succs) == 1:
                        target_block = succs[0]
                
                if target_block is not None and target_block in block_new_start:
                    new_target = block_new_start[target_block]
                    new_sbx = new_target - new_pc - 1
                    instr.sbx = new_sbx
                    instr.bx = new_sbx + 131071
                    instr.raw = (instr.opcode & 0x3F) | ((instr.a & 0xFF) << 6) | ((instr.bx & 0x3FFFF) << 14)
            
            elif instr.opcode == Opcode.FORPREP:
                # FORPREP jumps to FORLOOP (JUMP edge)
                target_block = None
                for succ_id in self.graph.successors(block_id):
                    edge_data = self.graph.edges[block_id, succ_id]
                    if edge_data.get('edge_type') == EdgeType.JUMP:
                        target_block = succ_id
                        break
                
                # Fallback: if no JUMP edge, use the only successor
                if target_block is None:
                    succs = list(self.graph.successors(block_id))
                    if len(succs) == 1:
                        target_block = succs[0]
                
                if target_block is not None and target_block in block_new_start:
                    new_target = block_new_start[target_block]
                    new_sbx = new_target - new_pc - 1
                    instr.sbx = new_sbx
                    instr.bx = new_sbx + 131071
                    instr.raw = (instr.opcode & 0x3F) | ((instr.a & 0xFF) << 6) | ((instr.bx & 0x3FFFF) << 14)
            
            elif instr.opcode == Opcode.FORLOOP:
                # FORLOOP jumps back to loop body (LOOP_BACK edge)
                target_block = None
                for succ_id in self.graph.successors(block_id):
                    edge_data = self.graph.edges[block_id, succ_id]
                    edge_type = edge_data.get('edge_type')
                    if edge_type == EdgeType.LOOP_BACK:
                        target_block = succ_id
                        break
                
                if target_block is not None and target_block in block_new_start:
                    new_target = block_new_start[target_block]
                    new_sbx = new_target - new_pc - 1
                    instr.sbx = new_sbx
                    instr.bx = new_sbx + 131071
                    instr.raw = (instr.opcode & 0x3F) | ((instr.a & 0xFF) << 6) | ((instr.bx & 0x3FFFF) << 14)
                # If target not found, keep original sbx (may cause issues but preserves behavior)
            
            elif instr.opcode == Opcode.TFORLOOP:
                # TFORLOOP jumps back to loop body (LOOP_BACK edge)
                target_block = None
                for succ_id in self.graph.successors(block_id):
                    edge_data = self.graph.edges[block_id, succ_id]
                    edge_type = edge_data.get('edge_type')
                    if edge_type == EdgeType.LOOP_BACK:
                        target_block = succ_id
                        break
                
                if target_block is not None and target_block in block_new_start:
                    new_target = block_new_start[target_block]
                    new_sbx = new_target - new_pc - 1
                    instr.sbx = new_sbx
                    instr.bx = new_sbx + 131071
                    instr.raw = (instr.opcode & 0x3F) | ((instr.a & 0xFF) << 6) | ((instr.bx & 0x3FFFF) << 14)
                # If target not found, keep original sbx
            
            elif instr.opcode == Opcode.LOADBOOL and instr.c != 0:
                # LOADBOOL with C != 0 skips the next instruction
                # Find the JUMP successor from CFG
                target_block = None
                for succ_id in self.graph.successors(block_id):
                    edge_data = self.graph.edges[block_id, succ_id]
                    if edge_data.get('edge_type') == EdgeType.JUMP:
                        target_block = succ_id
                        break
                
                # LOADBOOL always skips to pc+2, we need to verify the target
                # is correct. If target_block starts at expected position, it's fine
                # Otherwise we might need to adjust (but can't change C field semantics)
                if target_block is not None and target_block in block_new_start:
                    expected_skip_pc = new_pc + 2
                    actual_target_pc = block_new_start[target_block]
                    if expected_skip_pc != actual_target_pc:
                        # Warning: LOADBOOL skip target mismatch
                        # This can happen if dead code was removed between this LOADBOOL
                        # and its skip target. The only fix is to insert a NOP or JMP.
                        # For now, we just leave it (may break semantics)
                        pass
        
        return new_code
    
    def verify_integrity(self) -> Tuple[bool, List[str]]:
        """
        Verify the integrity of the CFG.
        
        Checks:
        1. Entry block exists and is reachable from itself
        2. All blocks have valid instruction ranges
        3. All edges point to valid blocks
        4. Conditional blocks have exactly 2 successors
        5. RETURN/TAILCALL blocks have no successors
        6. All non-exit blocks have at least one successor
        
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        # Check entry block
        if not self.entry_block:
            issues.append("No entry block found")
        
        # Check each block
        for block_id, block in self.blocks.items():
            # Check instruction range
            if block.start_pc < 0:
                issues.append(f"Block {block_id}: negative start_pc ({block.start_pc})")
            if block.end_pc <= block.start_pc:
                issues.append(f"Block {block_id}: invalid range [{block.start_pc}, {block.end_pc})")
            if block.end_pc > len(self.proto.code):
                issues.append(f"Block {block_id}: end_pc ({block.end_pc}) exceeds code length ({len(self.proto.code)})")
            
            # Check edges point to valid blocks
            for succ_id in self.graph.successors(block_id):
                if succ_id not in self.blocks:
                    issues.append(f"Block {block_id}: edge to non-existent block {succ_id}")
            
            # Check last instruction semantics
            if block.instructions:
                last_instr = block.instructions[-1]
                succs = list(self.graph.successors(block_id))
                
                # RETURN/TAILCALL should have no successors
                if last_instr.opcode in (Opcode.RETURN, Opcode.TAILCALL):
                    if succs:
                        issues.append(f"Block {block_id}: RETURN/TAILCALL has {len(succs)} successors")
                
                # Conditional instructions should have 2 successors
                elif last_instr.opcode in (Opcode.EQ, Opcode.LT, Opcode.LE,
                                           Opcode.NEQ, Opcode.GE, Opcode.GT,
                                           Opcode.TEST, Opcode.TESTSET):
                    if len(succs) != 2 and len(succs) != 1:
                        # 1 successor is OK if one branch was eliminated
                        issues.append(f"Block {block_id}: conditional has {len(succs)} successors (expected 1-2)")
                
                # Loop instructions should have 2 successors
                elif last_instr.opcode in (Opcode.FORLOOP, Opcode.TFORLOOP):
                    if len(succs) != 2:
                        issues.append(f"Block {block_id}: loop has {len(succs)} successors (expected 2)")
                
                # Non-terminator blocks should have at least 1 successor
                elif last_instr.opcode not in (Opcode.RETURN, Opcode.TAILCALL):
                    if not succs and not block.is_exit:
                        issues.append(f"Block {block_id}: non-exit block has no successors")
        
        # Check reachability
        unreachable = self.find_unreachable_blocks()
        if unreachable:
            issues.append(f"Unreachable blocks: {sorted(unreachable)}")
        
        return len(issues) == 0, issues
    
    def get_cfg_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the CFG.
        
        Returns:
            Dictionary with CFG statistics
        """
        from collections import Counter
        
        edge_types = Counter()
        for _, _, data in self.graph.edges(data=True):
            edge_types[data.get('edge_type', EdgeType.SEQUENTIAL).name] += 1
        
        return {
            'total_blocks': len(self.blocks),
            'total_edges': self.graph.number_of_edges(),
            'total_instructions': sum(len(b.instructions) for b in self.blocks.values()),
            'entry_block': self.entry_block.id if self.entry_block else None,
            'exit_blocks': [b.id for b in self.exit_blocks],
            'unreachable_blocks': len(self.find_unreachable_blocks()),
            'loops': len(self.find_loops()),
            'edge_types': dict(edge_types),
        }
    
    def redirect_edge(self, from_block: int, old_target: int, new_target: int, 
                      preserve_type: bool = True) -> bool:
        """
        Redirect an edge from one target to another.
        
        This is useful for deobfuscation when you want to change where a
        branch goes without modifying the block's instructions.
        
        Args:
            from_block: Source block ID
            old_target: Current target block ID
            new_target: New target block ID
            preserve_type: If True, preserve the edge type
        
        Returns:
            True if edge was redirected, False if edge not found
        """
        if not self.graph.has_edge(from_block, old_target):
            return False
        
        if new_target not in self.blocks:
            return False
        
        # Get edge data
        edge_data = dict(self.graph.edges[from_block, old_target])
        
        # Remove old edge
        self.graph.remove_edge(from_block, old_target)
        self.blocks[from_block].successors.discard(old_target)
        self.blocks[old_target].predecessors.discard(from_block)
        
        # Add new edge
        self.graph.add_edge(from_block, new_target, **edge_data)
        self.blocks[from_block].successors.add(new_target)
        self.blocks[new_target].predecessors.add(from_block)
        
        return True
    
    def remove_block(self, block_id: int) -> bool:
        """
        Remove a block from the CFG.
        
        This removes the block and all its edges. Callers should ensure
        the block is unreachable before removing.
        
        Args:
            block_id: Block ID to remove
        
        Returns:
            True if block was removed, False if not found
        """
        if block_id not in self.blocks:
            return False
        
        block = self.blocks[block_id]
        
        # Update predecessor/successor sets of connected blocks
        for succ_id in list(block.successors):
            if succ_id in self.blocks:
                self.blocks[succ_id].predecessors.discard(block_id)
        
        for pred_id in list(block.predecessors):
            if pred_id in self.blocks:
                self.blocks[pred_id].successors.discard(block_id)
        
        # Remove from graph
        if block_id in self.graph:
            self.graph.remove_node(block_id)
        
        # Remove from blocks dict
        del self.blocks[block_id]
        
        # Update pc_to_block mapping
        self.pc_to_block = {
            pc: bid for pc, bid in self.pc_to_block.items() if bid != block_id
        }
        
        return True

    def render(self, filepath: str, format: str = 'png', include_instructions: bool = True):
        """Render CFG to image using graphviz"""
        try:
            import graphviz
            dot = self.to_dot(include_instructions)
            source = graphviz.Source(dot)
            source.render(filepath, format=format, cleanup=True)
        except ImportError:
            print("graphviz package not installed. Install with: pip install graphviz")
            self.save_dot(filepath + '.dot', include_instructions)


def build_cfg(proto: Prototype) -> CFG:
    """Build a CFG for a prototype"""
    return CFG(proto)


def _build_closure_index(proto: Prototype, path: list = None, func_counter: list = None) -> dict:
    """
    Build a mapping from global function number (F0, F1, F2...) to (prototype, path).
    
    This mirrors the numbering used by list_closures in disassembler.py.
    
    Args:
        proto: The root prototype (main function)
        path: Current path (list of indices)
        func_counter: Global function counter
    
    Returns:
        Dict mapping global function number to (prototype, cli_selector_path)
    """
    if path is None:
        path = []
    if func_counter is None:
        func_counter = [0]
    
    result = {}
    
    # Process children with global counter
    if proto.protos:
        n = len(proto.protos)
        offset = func_counter[0]
        func_counter[0] += n
        
        for i, child in enumerate(proto.protos):
            child_path = path + [i]
            child_func_num = offset + i
            
            # Store the mapping: global number -> (prototype, path)
            result[child_func_num] = (child, child_path)
            
            # Recursively process grandchildren
            result.update(_build_closure_index(child, child_path, func_counter))
    
    return result


def _is_global_func_number(path: str) -> bool:
    """
    Check if the path is a simple global function number like "F19" or "19".
    
    A global function number has no slashes or dashes, and is just a single number
    after the optional 'F' prefix.
    
    Args:
        path: The path string to check
    
    Returns:
        True if it's a simple global function number (no path separators)
    """
    cleaned = path.lstrip('Ff')
    # If there are no path separators and it's a single number
    if '/' not in cleaned and '-' not in cleaned and ' ' not in cleaned:
        try:
            int(cleaned)
            return True
        except ValueError:
            return False
    return False


def get_prototype_by_path(proto: Prototype, path: str) -> Prototype:
    """
    Get a prototype by its path specification.
    
    Supports two selection methods:
    1. Global function number (display_name): F19, F6, etc.
       - Uses the global counter shown in 'list' command output
    2. Path notation (cli_selector): F0/2/9/1, F0/1, etc.
       - First level (main's children): 0-based (F0, F1...)
       - Nested levels: 1-based (F1, F2...)
    
    Args:
        proto: The root prototype (main function)
        path: Either:
              - Global number like "F19", "19" (no slashes)
              - Path like "F0", "F0/1", "F0/2/3", or "" for main
    
    Returns:
        The prototype at the specified path
    
    Raises:
        ValueError: If the path is invalid
    """
    if not path or path.lower() == "main":
        return proto
    
    # Check if it's a global function number (no path separators)
    if _is_global_func_number(path):
        func_num = int(path.lstrip('Ff'))
        
        # Build the closure index to find the prototype by global number
        closure_index = _build_closure_index(proto)
        
        if func_num not in closure_index:
            max_num = max(closure_index.keys()) if closure_index else -1
            if max_num >= 0:
                raise ValueError(f"Function F{func_num} not found (valid range: F0-F{max_num})")
            else:
                raise ValueError(f"Function F{func_num} not found (no child functions)")
        
        return closure_index[func_num][0]
    
    # Otherwise, parse as path notation (F0/2/3)
    path = path.lstrip('Ff')
    parts = path.replace('/', ' ').replace('-', ' ').split()
    
    current = proto
    for i, part in enumerate(parts):
        try:
            num = int(part)
            if i == 0:
                # First level: 0-based (F0, F1...)
                idx = num
            else:
                # Nested levels: 1-based (F1, F2...) → convert to 0-based
                idx = num - 1
                if idx < 0:
                    raise ValueError(f"Invalid function number at level {i+2}: {part} (must be >= 1)")
            
            if idx >= len(current.protos):
                if i == 0:
                    raise ValueError(f"Child function F{num} not found (only {len(current.protos)} children)")
                else:
                    raise ValueError(f"Child function F{num} not found at level {i+2} (only {len(current.protos)} children)")
            current = current.protos[idx]
        except ValueError as e:
            if "not found" in str(e) or "Invalid function" in str(e):
                raise
            raise ValueError(f"Invalid path component: {part}")
    
    return current


def build_cfg_for_closure(chunk, closure_path: str = None) -> CFG:
    """
    Build a CFG for a specific closure.
    
    Args:
        chunk: LuaChunk containing the bytecode
        closure_path: Path to the closure (e.g., "F0", "F0/1"), or None for main
    
    Returns:
        CFG for the specified closure
    """
    proto = get_prototype_by_path(chunk.main, closure_path) if closure_path else chunk.main
    return CFG(proto)
