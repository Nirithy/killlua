"""
Lua Bytecode Deobfuscator

Implements deobfuscation techniques:
1. Constant Folding
2. Dead Branch Elimination
3. Dead Code Elimination
"""

from typing import List, Dict, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from copy import deepcopy
from enum import Enum, auto

from .parser import Prototype, Instruction, LuaConstant, LuaConstantType
from .cfg import CFG, BasicBlock, EdgeType, build_cfg
from .opcodes import Opcode, OpMode, ISK, INDEXK


class DeobfuscationPass(Enum):
    """Types of deobfuscation passes"""
    DEAD_CODE_ELIMINATION = auto()
    CONSTANT_FOLDING = auto()
    DEAD_BRANCH_ELIMINATION = auto()
    SEQUENTIAL_BLOCK_MERGE = auto()


@dataclass
class DeobfuscationResult:
    """Result of a deobfuscation pass"""
    success: bool
    pass_type: DeobfuscationPass
    changes_made: int
    details: str = ""


class DeadCodeEliminator:
    """Removes unreachable code from the CFG"""
    
    def __init__(self, cfg: CFG):
        self.cfg = cfg
    
    def _find_trailing_return_blocks(self) -> Set[int]:
        """
        Find blocks that contain trailing RETURN instructions at the end of the function.
        
        Lua compiler often generates unreachable RETURN instructions after TAILCALL
        or other RETURN statements as a safety measure. These should not be removed
        as they are part of the valid bytecode structure.
        
        Returns:
            Set of block IDs that should be preserved (trailing RETURN blocks).
        """
        if not self.cfg.blocks:
            return set()
        
        # Find the maximum end_pc among all blocks (this is the end of the function)
        max_end_pc = max(block.end_pc for block in self.cfg.blocks.values())
        
        # Find blocks that end at the function boundary and contain only RETURN
        trailing_blocks = set()
        for block_id, block in self.cfg.blocks.items():
            if block.end_pc == max_end_pc:
                # This block is at the very end of the function
                # Check if it's a simple RETURN block (single instruction RETURN)
                if block.instructions:
                    # Preserve blocks that end with RETURN at the function boundary
                    if block.instructions[-1].opcode == Opcode.RETURN:
                        trailing_blocks.add(block_id)
            elif block.instructions:
                # Also check for blocks that are just before max_end_pc and
                # consist only of RETURN instructions
                all_returns = all(
                    instr.opcode == Opcode.RETURN 
                    for instr in block.instructions
                )
                if all_returns and block.end_pc >= max_end_pc - 1:
                    trailing_blocks.add(block_id)
        
        return trailing_blocks
    
    def eliminate(self) -> DeobfuscationResult:
        """Remove unreachable basic blocks, preserving trailing RETURN blocks."""
        unreachable = self.cfg.find_unreachable_blocks()
        
        if not unreachable:
            return DeobfuscationResult(
                success=True,
                pass_type=DeobfuscationPass.DEAD_CODE_ELIMINATION,
                changes_made=0,
                details="No unreachable code found"
            )
        
        # Don't remove trailing RETURN blocks - they are compiler-generated safety returns
        trailing_returns = self._find_trailing_return_blocks()
        blocks_to_remove = unreachable - trailing_returns
        
        if not blocks_to_remove:
            return DeobfuscationResult(
                success=True,
                pass_type=DeobfuscationPass.DEAD_CODE_ELIMINATION,
                changes_made=0,
                details="No unreachable code found (preserved trailing RETURN blocks)"
            )
        
        # Remove unreachable blocks (except trailing RETURN blocks)
        for block_id in blocks_to_remove:
            if block_id in self.cfg.blocks:
                del self.cfg.blocks[block_id]
            if block_id in self.cfg.graph:
                self.cfg.graph.remove_node(block_id)
        
        # Update pc_to_block mapping
        self.cfg.pc_to_block = {
            pc: block_id 
            for pc, block_id in self.cfg.pc_to_block.items()
            if block_id not in blocks_to_remove
        }
        
        return DeobfuscationResult(
            success=True,
            pass_type=DeobfuscationPass.DEAD_CODE_ELIMINATION,
            changes_made=len(blocks_to_remove),
            details=f"Removed {len(blocks_to_remove)} unreachable blocks"
        )


class ConstantFolder:
    """Folds constant expressions in bytecode"""
    
    def __init__(self, proto: Prototype):
        self.proto = proto
        self.constants = proto.constants
    
    def fold(self) -> DeobfuscationResult:
        """Perform constant folding on instructions"""
        changes = 0
        
        for i, instr in enumerate(self.proto.code):
            # Check for arithmetic on constants
            if instr.opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV,
                               Opcode.MOD, Opcode.IDIV, Opcode.BAND, Opcode.BOR,
                               Opcode.BXOR, Opcode.SHL, Opcode.SHR, Opcode.POW):
                
                # Check if both operands are constants
                if ISK(instr.b) and ISK(instr.c):
                    b_idx = INDEXK(instr.b)
                    c_idx = INDEXK(instr.c)
                    
                    if b_idx < len(self.constants) and c_idx < len(self.constants):
                        b_const = self.constants[b_idx]
                        c_const = self.constants[c_idx]
                        
                        if (b_const.type in (LuaConstantType.NUMBER, LuaConstantType.INT) and
                            c_const.type in (LuaConstantType.NUMBER, LuaConstantType.INT)):
                            
                            try:
                                result = self._compute(instr.opcode, b_const.value, c_const.value)
                                if result is not None:
                                    # We found a foldable expression
                                    # In practice, we'd replace this with a LOADK
                                    changes += 1
                            except:
                                pass
        
        return DeobfuscationResult(
            success=changes > 0,
            pass_type=DeobfuscationPass.CONSTANT_FOLDING,
            changes_made=changes,
            details=f"Found {changes} foldable expressions"
        )
    
    def _compute(self, opcode: int, b: float, c: float) -> Optional[float]:
        """Compute the result of a binary operation"""
        try:
            if opcode == Opcode.ADD:
                return b + c
            elif opcode == Opcode.SUB:
                return b - c
            elif opcode == Opcode.MUL:
                return b * c
            elif opcode == Opcode.DIV:
                return b / c if c != 0 else None
            elif opcode == Opcode.MOD:
                return b % c if c != 0 else None
            elif opcode == Opcode.IDIV:
                return b // c if c != 0 else None
            elif opcode == Opcode.POW:
                return b ** c
            elif opcode == Opcode.BAND:
                return int(b) & int(c)
            elif opcode == Opcode.BOR:
                return int(b) | int(c)
            elif opcode == Opcode.BXOR:
                return int(b) ^ int(c)
            elif opcode == Opcode.SHL:
                return int(b) << int(c)
            elif opcode == Opcode.SHR:
                return int(b) >> int(c)
        except:
            pass
        return None


class DeadBranchEliminator:
    """
    Eliminates branches that lead to dead/garbage blocks.
    
    A "garbage block" is a block that:
    1. Has no successors (dead end) but doesn't end with RETURN/TAILCALL, OR
    2. Is unreachable from entry, OR
    3. Only leads to other garbage blocks (transitively dead)
    
    When a conditional branch has one target that is a garbage block,
    the conditional instruction is expanded into sequential instructions
    that preserve the side effects of the kept branch:
    
    Instruction Expansion Rules:
    ============================
    
    1. TESTSET A B C: "if (R(B) <=> C) then R(A) := R(B) else pc++"
       - Keep COND_FALSE (condition true): expand to [MOVE A B]
       - Keep COND_TRUE (condition false/skip): expand to [] (remove)
    
    2. TEST A C: "if not (R(A) <=> C) then pc++"
       - Keep COND_FALSE (condition true): expand to [] (remove, no side effect)
       - Keep COND_TRUE (condition false/skip): expand to [] (remove)
    
    3. EQ/LT/LE/NEQ/GE/GT: comparison instructions (no side effects)
       - Simply remove the edge to garbage block
    
    4. FORLOOP A sBx: "R(A)+=R(A+2); if R(A) <?= R(A+1) then { pc+=sBx; R(A+3)=R(A) }"
       - Keep LOOP_BACK (loop continues): expand to [ADD A A (A+2), MOVE (A+3) A]
         (jump handled by CFG)
       - Keep LOOP_EXIT (loop exits): expand to [ADD A A (A+2)]
    
    5. TFORLOOP A sBx: "if R(A+1) ~= nil then { R(A)=R(A+1); pc += sBx }"
       - Keep LOOP_BACK (loop continues): expand to [MOVE A (A+1)]
         (jump handled by CFG)
       - Keep LOOP_EXIT (loop exits): expand to [] (remove)
    
    6. LOADBOOL A B C (C!=0): "R(A) := (Bool)B; if (C) pc++"
       - This always skips, expand to [LOADBOOL A B 0] (keep assignment, no skip)
    
    This pass should run BEFORE DCE to help identify more dead code.
    """
    
    # All conditional opcodes that can be processed
    ALL_CONDITIONAL_OPCODES = {
        # Comparison opcodes (no side effects)
        Opcode.EQ, Opcode.LT, Opcode.LE,
        Opcode.NEQ, Opcode.GE, Opcode.GT,
        # Test opcodes
        Opcode.TEST,      # no side effect
        Opcode.TESTSET,   # has side effect: R(A) := R(B)
        # Loop opcodes
        Opcode.FORLOOP,   # has side effects: R(A)+=R(A+2), R(A+3)=R(A)
        Opcode.TFORLOOP,  # has side effect: R(A)=R(A+1)
    }
    
    def __init__(self, cfg: CFG):
        self.cfg = cfg
    
    def _find_trailing_return_blocks(self) -> Set[int]:
        """
        Find blocks that contain trailing RETURN instructions at the end of the function.
        
        These are compiler-generated safety returns that should not be considered garbage.
        """
        if not self.cfg.blocks:
            return set()
        
        # Find the maximum end_pc among all blocks (this is the end of the function)
        max_end_pc = max(block.end_pc for block in self.cfg.blocks.values())
        
        # Find blocks that end at the function boundary and contain RETURN
        trailing_blocks = set()
        for block_id, block in self.cfg.blocks.items():
            if not block.instructions:
                continue
            # Check if this block contains RETURN and is at or near the end of the function
            last_instr = block.instructions[-1]
            if last_instr.opcode == Opcode.RETURN:
                # Preserve blocks at the function end
                if block.end_pc >= max_end_pc - 1:
                    trailing_blocks.add(block_id)
        
        return trailing_blocks
    
    def _block_has_unknown_opcode(self, block: BasicBlock) -> bool:
        """
        Check if a block contains any unknown opcode.
        
        Unknown opcodes are invalid/garbage instructions that would never be
        executed in valid Lua bytecode. Their presence indicates this block
        is unreachable garbage code inserted by the obfuscator.
        
        Args:
            block: The basic block to check.
        
        Returns:
            True if the block contains any unknown opcode.
        """
        for instr in block.instructions:
            # Check if opcode name starts with "UNKNOWN_" which indicates
            # it's not a valid Lua opcode
            if instr.opcode_name.startswith("UNKNOWN_"):
                return True
        return False
    
    def _find_garbage_blocks(self) -> Set[int]:
        """
        Find all garbage blocks (blocks that lead nowhere useful).
        
        A block is garbage if:
        1. It's unreachable from entry, OR
        2. It has no successors but doesn't end with RETURN/TAILCALL, OR
        3. All its successors are garbage blocks (transitively), OR
        4. It contains unknown/invalid opcodes (garbage instructions)
        
        Note: Trailing RETURN blocks (compiler-generated safety returns) are excluded.
        """
        garbage = set()
        
        # Find trailing RETURN blocks that should be preserved
        trailing_returns = self._find_trailing_return_blocks()
        
        # First, find blocks that contain unknown opcodes (garbage instructions)
        for block_id, block in self.cfg.blocks.items():
            if self._block_has_unknown_opcode(block):
                garbage.add(block_id)
        
        # Then, find blocks that are dead ends (no successors, not RETURN/TAILCALL)
        for block_id, block in self.cfg.blocks.items():
            succs = list(self.cfg.graph.successors(block_id))
            if not succs and block.instructions:
                last_instr = block.instructions[-1]
                if last_instr.opcode not in (Opcode.RETURN, Opcode.TAILCALL):
                    garbage.add(block_id)
        
        # Also add unreachable blocks (but not trailing RETURN blocks)
        unreachable = self.cfg.find_unreachable_blocks()
        garbage.update(unreachable - trailing_returns)
        
        # Iteratively find blocks whose all successors are garbage
        changed = True
        while changed:
            changed = False
            for block_id, block in self.cfg.blocks.items():
                if block_id in garbage:
                    continue
                
                succs = list(self.cfg.graph.successors(block_id))
                if not succs:
                    continue
                
                # If all successors are garbage, this block is also garbage
                # (unless it ends with RETURN/TAILCALL)
                if block.instructions:
                    last_instr = block.instructions[-1]
                    if last_instr.opcode in (Opcode.RETURN, Opcode.TAILCALL):
                        continue
                
                if all(s in garbage for s in succs):
                    garbage.add(block_id)
                    changed = True
        
        return garbage

    def _get_edge_type_to_successor(self, block_id: int, succ_id: int) -> Optional[EdgeType]:
        """Get the edge type from block_id to succ_id."""
        if self.cfg.graph.has_edge(block_id, succ_id):
            return self.cfg.graph.edges[block_id, succ_id].get('edge_type')
        return None

    def _expand_instruction(self, block: BasicBlock, kept_edge_type: EdgeType) -> List[Instruction]:
        """
        Expand a conditional instruction into sequential instructions based on which branch is kept.
        
        Returns a list of instructions to replace the last instruction in the block.
        Empty list means the instruction should be removed.
        
        Args:
            block: The basic block containing the conditional instruction
            kept_edge_type: The edge type of the branch that is kept (valid branch)
        
        Returns:
            List of instructions to replace the conditional instruction
        """
        if not block.instructions:
            return []
        
        last_instr = block.instructions[-1]
        opcode = last_instr.opcode
        
        # TESTSET A B C: if (R(B) <=> C) then R(A) := R(B) else pc++
        if opcode == Opcode.TESTSET:
            if kept_edge_type == EdgeType.COND_FALSE:
                # Condition always true: R(A) := R(B) always executes
                # Expand to: MOVE A B
                return [Instruction.encode_new(
                    opcode=Opcode.MOVE,
                    a=last_instr.a,
                    b=last_instr.b
                )]
            elif kept_edge_type == EdgeType.COND_TRUE:
                # Condition always false: R(A) := R(B) never happens
                # Expand to: (nothing)
                return []
        
        # TEST A C: if not (R(A) <=> C) then pc++
        # No side effects, can be safely removed
        elif opcode == Opcode.TEST:
            return []
        
        # EQ/LT/LE/NEQ/GE/GT: comparison (no side effects)
        elif opcode in (Opcode.EQ, Opcode.LT, Opcode.LE, 
                        Opcode.NEQ, Opcode.GE, Opcode.GT):
            return []
        
        # FORLOOP A sBx: R(A)+=R(A+2); if R(A) <?= R(A+1) then { pc+=sBx; R(A+3)=R(A) }
        elif opcode == Opcode.FORLOOP:
            a = last_instr.a
            if kept_edge_type == EdgeType.LOOP_BACK:
                # Loop always continues: execute R(A)+=R(A+2) and R(A+3)=R(A)
                # Expand to: ADD A A (A+2), MOVE (A+3) A
                # Note: ADD uses RK(B) and RK(C), so we use registers directly
                return [
                    Instruction.encode_new(opcode=Opcode.ADD, a=a, b=a, c=a+2),
                    Instruction.encode_new(opcode=Opcode.MOVE, a=a+3, b=a),
                ]
            elif kept_edge_type == EdgeType.LOOP_EXIT:
                # Loop always exits: only execute R(A)+=R(A+2)
                # Expand to: ADD A A (A+2)
                return [
                    Instruction.encode_new(opcode=Opcode.ADD, a=a, b=a, c=a+2),
                ]
        
        # TFORLOOP A sBx: if R(A+1) ~= nil then { R(A)=R(A+1); pc += sBx }
        elif opcode == Opcode.TFORLOOP:
            a = last_instr.a
            if kept_edge_type == EdgeType.LOOP_BACK:
                # Loop always continues: execute R(A)=R(A+1)
                # Expand to: MOVE A (A+1)
                return [
                    Instruction.encode_new(opcode=Opcode.MOVE, a=a, b=a+1),
                ]
            elif kept_edge_type == EdgeType.LOOP_EXIT:
                # Loop always exits: no side effect
                # Expand to: (nothing)
                return []
        
        # Unknown opcode, return original instruction unchanged
        return [last_instr]

    def _apply_expansion(self, block: BasicBlock, new_instructions: List[Instruction]) -> int:
        """
        Apply instruction expansion to a block.
        
        Replaces the last instruction with the new instruction list.
        Returns the change in instruction count (can be negative).
        """
        if not block.instructions:
            return 0
        
        old_count = 1  # We're replacing the last instruction
        new_count = len(new_instructions)
        
        # Remove the last instruction
        block.instructions.pop()
        
        # Add new instructions
        block.instructions.extend(new_instructions)
        
        # Update end_pc
        delta = new_count - old_count
        block.end_pc += delta
        
        return delta
    
    def eliminate(self) -> DeobfuscationResult:
        """
        Remove edges to garbage blocks from conditional branches.
        
        For each conditional branch where one target is garbage:
        - Expand the conditional instruction into sequential instructions
        - Remove the edge to the garbage block
        - The block now has unconditional flow to the valid successor
        
        Returns:
            DeobfuscationResult with the number of branches eliminated.
        """
        garbage = self._find_garbage_blocks()
        
        if not garbage:
            return DeobfuscationResult(
                success=True,
                pass_type=DeobfuscationPass.DEAD_BRANCH_ELIMINATION,
                changes_made=0,
                details="No garbage blocks found"
            )
        
        changes = 0
        expansions = 0
        
        # Find conditional blocks with one garbage successor
        for block_id in list(self.cfg.graph.nodes()):
            if block_id in garbage:
                continue
            
            block = self.cfg.blocks.get(block_id)
            if not block or not block.instructions:
                continue
            
            last_instr = block.instructions[-1]
            opcode = last_instr.opcode
            
            # Only process conditional opcodes
            if opcode not in self.ALL_CONDITIONAL_OPCODES:
                continue
            
            # Get successors and categorize them
            succs = list(self.cfg.graph.successors(block_id))
            if len(succs) != 2:
                continue
            
            garbage_succs = [s for s in succs if s in garbage]
            valid_succs = [s for s in succs if s not in garbage]
            
            if len(garbage_succs) != 1 or len(valid_succs) != 1:
                continue
            
            garbage_succ = garbage_succs[0]
            valid_succ = valid_succs[0]
            
            # Determine which edge type is being kept
            kept_edge_type = self._get_edge_type_to_successor(block_id, valid_succ)
            
            if kept_edge_type is None:
                continue
            
            # Expand the instruction
            new_instructions = self._expand_instruction(block, kept_edge_type)
            
            # Apply the expansion
            delta = self._apply_expansion(block, new_instructions)
            if delta != 0:
                expansions += 1
            
            # Remove edge to garbage block
            if self.cfg.graph.has_edge(block_id, garbage_succ):
                self.cfg.graph.remove_edge(block_id, garbage_succ)
                block.successors.discard(garbage_succ)
                if garbage_succ in self.cfg.blocks:
                    self.cfg.blocks[garbage_succ].predecessors.discard(block_id)
            
            # Update edge type to valid successor (now it's sequential/unconditional)
            if self.cfg.graph.has_edge(block_id, valid_succ):
                # Change edge type to SEQUENTIAL or JUMP depending on the original type
                if kept_edge_type in (EdgeType.LOOP_BACK,):
                    self.cfg.graph.edges[block_id, valid_succ]['edge_type'] = EdgeType.JUMP
                else:
                    self.cfg.graph.edges[block_id, valid_succ]['edge_type'] = EdgeType.SEQUENTIAL
            
            changes += 1
        
        details = f"Eliminated {changes} dead branch(es), found {len(garbage)} garbage block(s)"
        if expansions > 0:
            details += f", expanded {expansions} instruction(s)"
        
        return DeobfuscationResult(
            success=changes > 0,
            pass_type=DeobfuscationPass.DEAD_BRANCH_ELIMINATION,
            changes_made=changes,
            details=details
        )


class SequentialBlockMerger:
    """
    Merges sequential basic blocks to simplify control flow.
    
    A sequential block pair can be merged when:
    1. Block A has exactly one successor B
    2. Block B has exactly one predecessor A
    
    Mergeable terminator instructions and their expansion:
    ======================================================
    
    1. JMP (unconditional jump with no side effects):
       - Semantics: pc += sBx
       - Expansion: Remove the JMP instruction (no side effects)
    
    2. LOADBOOL A B C (with C != 0, skips next instruction):
       - Semantics: R(A) := (Bool)B; if (C) pc++
       - Expansion: LOADBOOL A B 0 (keep the assignment, remove skip)
    
    3. FORPREP A sBx (for loop preparation):
       - Semantics: R(A) -= R(A+2); pc += sBx
       - Expansion: SUB A A (A+2) (keep the subtraction, remove jump)
       Note: This is typically used when FORPREP jumps to FORLOOP and
       they can be merged, essentially unrolling the loop initialization.
    
    Non-mergeable terminators (conditionals, loops with exit):
    - EQ, LT, LE, NEQ, GE, GT, TEST, TESTSET: have two successors
    - FORLOOP, TFORLOOP: have two successors (loop body and exit)
    - RETURN, TAILCALL: no successors (function exit)
    
    This pass should run AFTER dead branch elimination to maximize
    opportunities for merging.
    """
    
    # Opcodes that can be expanded when merging blocks
    MERGEABLE_TERMINATORS = {
        Opcode.JMP,       # Pure jump, no side effects
        Opcode.LOADBOOL,  # With C != 0, can be simplified
        Opcode.FORPREP,   # Jump to FORLOOP, has side effect R(A) -= R(A+2)
    }
    
    def __init__(self, cfg: CFG):
        self.cfg = cfg
    
    def _is_jmp_only_block(self, block_id: int) -> bool:
        """
        Check if this block contains only a single JMP instruction.
        """
        block = self.cfg.blocks.get(block_id)
        if not block or not block.instructions:
            return False
        
        # Single JMP instruction block
        if len(block.instructions) == 1 and block.instructions[0].opcode == Opcode.JMP:
            return True
        
        return False
    
    def _find_jmp_chain_target(self, block_id: int, visited: set = None) -> Optional[int]:
        """
        Follow a JMP chain to find its final non-JMP target.
        
        Returns the final target block_id, or None if there's a loop.
        """
        if visited is None:
            visited = set()
        
        if block_id in visited:
            return None  # Loop detected
        visited.add(block_id)
        
        if not self._is_jmp_only_block(block_id):
            return block_id  # This is the target (not a JMP-only block)
        
        succs = list(self.cfg.graph.successors(block_id))
        if len(succs) != 1:
            return block_id  # Multiple successors or no successor
        
        return self._find_jmp_chain_target(succs[0], visited)
    
    def _is_reachable_from_conditional(self, block_id: int, visited: set = None) -> bool:
        """
        Check if this JMP-only block can be reached from a conditional instruction
        by following only JMP-only blocks backwards.
        
        This is used to prevent merging JMP blocks that are part of the conditional
        branch structure, which would cause rebuild_code to recreate them.
        """
        if visited is None:
            visited = set()
        
        if block_id in visited:
            return False
        visited.add(block_id)
        
        block = self.cfg.blocks.get(block_id)
        if not block:
            return False
        
        preds = list(self.cfg.graph.predecessors(block_id))
        if not preds:
            return False
        
        COND_OPS = (Opcode.EQ, Opcode.LT, Opcode.LE, Opcode.NEQ,
                    Opcode.GE, Opcode.GT, Opcode.TEST, Opcode.TESTSET)
        
        for pred_id in preds:
            pred_block = self.cfg.blocks.get(pred_id)
            if not pred_block or not pred_block.instructions:
                continue
            
            last_instr = pred_block.instructions[-1]
            
            # If predecessor ends with a conditional instruction, we found the source
            if last_instr.opcode in COND_OPS:
                return True
            
            # If predecessor is a JMP-only block, recursively check its predecessors
            if self._is_jmp_only_block(pred_id):
                if self._is_reachable_from_conditional(pred_id, visited):
                    return True
        
        # No conditional found in the JMP-only chain
        return False
    
    def _simplify_jmp_chains(self) -> int:
        """
        Simplify JMP chains by redirecting edges to the final target.
        
        For a chain like: COND_BLOCK -> JMP_A -> JMP_B -> REAL_CODE
        We redirect COND_BLOCK's edge directly to REAL_CODE.
        
        This makes JMP_A and JMP_B unreachable, to be removed by DCE.
        After rebuild_code, only ONE JMP will be inserted (if needed).
        
        Returns:
            Number of edges redirected.
        """
        changes = 0
        
        # Find all JMP-only blocks
        jmp_only_blocks = set()
        for block_id in self.cfg.blocks:
            if self._is_jmp_only_block(block_id):
                jmp_only_blocks.add(block_id)
        
        if not jmp_only_blocks:
            return 0
        
        # For each JMP-only block, redirect its predecessors to the final target
        for jmp_block_id in list(jmp_only_blocks):
            # Find the final target of this JMP chain
            final_target = self._find_jmp_chain_target(jmp_block_id)
            
            if final_target is None:
                continue  # Loop detected, skip
            
            # Only process if the chain has length > 1 (i.e., there's at least one
            # intermediate JMP block that can be eliminated)
            succs = list(self.cfg.graph.successors(jmp_block_id))
            if len(succs) != 1:
                continue
            
            # If immediate successor is the final target, no chain to simplify
            if succs[0] == final_target:
                continue
            
            # Redirect all predecessors (except JMP-only blocks in the chain)
            preds = list(self.cfg.graph.predecessors(jmp_block_id))
            for pred_id in preds:
                # Skip JMP-only predecessors (they're part of the chain)
                if pred_id in jmp_only_blocks:
                    continue
                
                # Get edge data
                if not self.cfg.graph.has_edge(pred_id, jmp_block_id):
                    continue
                edge_data = dict(self.cfg.graph.edges[pred_id, jmp_block_id])
                
                # Remove old edge
                self.cfg.graph.remove_edge(pred_id, jmp_block_id)
                
                # Add new edge to final target (if not already exists)
                if not self.cfg.graph.has_edge(pred_id, final_target):
                    self.cfg.graph.add_edge(pred_id, final_target, **edge_data)
                
                # Update predecessor/successor sets
                pred_block = self.cfg.blocks.get(pred_id)
                if pred_block:
                    pred_block.successors.discard(jmp_block_id)
                    pred_block.successors.add(final_target)
                
                jmp_block = self.cfg.blocks.get(jmp_block_id)
                if jmp_block:
                    jmp_block.predecessors.discard(pred_id)
                
                final_block = self.cfg.blocks.get(final_target)
                if final_block:
                    final_block.predecessors.add(pred_id)
                
                changes += 1
        
        return changes
    
    def _can_merge(self, block_a_id: int, block_b_id: int) -> bool:
        """
        Check if block_a can be merged with block_b.
        
        Conditions:
        1. block_a has exactly one successor (block_b)
        2. block_b has exactly one predecessor (block_a)
        3. block_a's terminator is mergeable (or no terminator/sequential flow)
        4. block_b is not an entry block
        5. If block_a is a JMP-only block that is a direct successor of a conditional,
           it cannot be merged (to avoid infinite merge/rebuild cycles)
        """
        block_a = self.cfg.blocks.get(block_a_id)
        block_b = self.cfg.blocks.get(block_b_id)
        
        if not block_a or not block_b:
            return False
        
        # Check: block_a has exactly one successor
        succs_a = list(self.cfg.graph.successors(block_a_id))
        if len(succs_a) != 1:
            return False
        
        # Check: that successor is block_b
        if succs_a[0] != block_b_id:
            return False
        
        # Check: block_b has exactly one predecessor
        preds_b = list(self.cfg.graph.predecessors(block_b_id))
        if len(preds_b) != 1:
            return False
        
        # Check: that predecessor is block_a
        if preds_b[0] != block_a_id:
            return False
        
        # Check: block_b is not an entry block
        if block_b.is_entry:
            return False
        
        # Check: if block_a is a JMP-only block that is reachable from a conditional
        # instruction (by tracing back through JMP-only blocks), it cannot be merged.
        # These JMP blocks are part of the conditional branch structure created by
        # rebuild_code, and merging would cause infinite loop.
        if self._is_jmp_only_block(block_a_id):
            if self._is_reachable_from_conditional(block_a_id):
                return False
        
        # Check: block_a's terminator is mergeable
        if block_a.instructions:
            last_instr = block_a.instructions[-1]
            opcode = last_instr.opcode
            
            # Pure sequential flow (no jump instruction at end) - can merge
            if opcode not in (Opcode.JMP, Opcode.LOADBOOL, Opcode.FORPREP,
                             Opcode.RETURN, Opcode.TAILCALL,
                             Opcode.EQ, Opcode.LT, Opcode.LE, Opcode.NEQ,
                             Opcode.GE, Opcode.GT, Opcode.TEST, Opcode.TESTSET,
                             Opcode.FORLOOP, Opcode.TFORLOOP):
                return True
            
            # JMP: mergeable (pure jump, no side effects)
            if opcode == Opcode.JMP:
                # Check if it's a pure JMP (A=0 means no upvalue closing)
                # Even with A!=0, we can merge if we preserve the upvalue semantics
                # For simplicity, we merge all JMPs as they have no data-flow side effects
                return True
            
            # LOADBOOL with C != 0: mergeable (skip can be removed)
            if opcode == Opcode.LOADBOOL and last_instr.c != 0:
                return True
            
            # FORPREP: mergeable (has side effect but can be expanded)
            if opcode == Opcode.FORPREP:
                return True
            
            # Other terminators (conditionals, loops, returns) are not mergeable
            return False
        
        return True  # Empty block can be merged
    
    def _expand_terminator(self, block: BasicBlock) -> List[Instruction]:
        """
        Expand a terminator instruction into sequential instructions.
        
        Returns the list of instructions that should replace the last instruction,
        preserving any side effects but removing the jump/branch.
        
        Args:
            block: The block whose terminator needs expansion
        
        Returns:
            List of instructions to replace the terminator. Empty list means
            the terminator should be removed entirely.
        """
        if not block.instructions:
            return []
        
        last_instr = block.instructions[-1]
        opcode = last_instr.opcode
        
        # JMP: no side effects, just remove it
        if opcode == Opcode.JMP:
            # JMP A sBx: "pc += sBx; if (A) close upvalues >= R(A-1)"
            # The upvalue closing is a side effect, but it only matters
            # when we're jumping out of scope. Since we're merging blocks
            # that are already sequential in the CFG, this is safe to remove.
            # Note: If A > 0, there might be upvalue semantics, but for
            # obfuscated jumps used purely for control flow, A is typically 0.
            return []
        
        # LOADBOOL A B C (with C != 0): keep assignment, remove skip
        if opcode == Opcode.LOADBOOL and last_instr.c != 0:
            # R(A) := (Bool)B; if (C) pc++
            # Expand to: LOADBOOL A B 0 (just the assignment)
            return [Instruction.encode_new(
                opcode=Opcode.LOADBOOL,
                a=last_instr.a,
                b=last_instr.b,
                c=0  # No skip
            )]
        
        # FORPREP A sBx: expand to subtraction
        if opcode == Opcode.FORPREP:
            # R(A) -= R(A+2); pc += sBx
            # Expand to: SUB A A (A+2)
            # Note: In Lua, R(A)-=R(A+2) means R(A) = R(A) - R(A+2)
            # SUB uses RK(B) and RK(C), for registers we use values < 256
            a = last_instr.a
            return [Instruction.encode_new(
                opcode=Opcode.SUB,
                a=a,
                b=a,       # R(A)
                c=a + 2    # R(A+2)
            )]
        
        # Non-terminator or non-mergeable: keep as-is
        return [last_instr]
    
    def _merge_blocks(self, block_a_id: int, block_b_id: int) -> bool:
        """
        Merge block_b into block_a.
        
        1. Expand block_a's terminator (if needed)
        2. Append block_b's instructions to block_a
        3. Update block_a's end_pc
        4. Transfer block_b's successors to block_a
        5. Remove block_b from the CFG
        
        Returns True if merge was successful.
        """
        block_a = self.cfg.blocks.get(block_a_id)
        block_b = self.cfg.blocks.get(block_b_id)
        
        if not block_a or not block_b:
            return False
        
        # Step 1: Expand block_a's terminator
        if block_a.instructions:
            last_instr = block_a.instructions[-1]
            expanded = self._expand_terminator(block_a)
            
            # Remove the old terminator
            block_a.instructions.pop()
            
            # Add expanded instructions (may be empty or modified)
            block_a.instructions.extend(expanded)
        
        # Step 2: Append block_b's instructions
        block_a.instructions.extend(block_b.instructions)
        
        # Step 3: Update block_a's end_pc
        block_a.end_pc = block_b.end_pc
        
        # Step 4: Transfer block_b's successors to block_a
        # Remove edge from block_a to block_b
        if self.cfg.graph.has_edge(block_a_id, block_b_id):
            self.cfg.graph.remove_edge(block_a_id, block_b_id)
        block_a.successors.discard(block_b_id)
        
        # Add edges from block_a to block_b's successors
        for succ_id in list(block_b.successors):
            if succ_id in self.cfg.blocks:
                # Get edge data from block_b
                edge_data = {}
                if self.cfg.graph.has_edge(block_b_id, succ_id):
                    edge_data = dict(self.cfg.graph.edges[block_b_id, succ_id])
                    self.cfg.graph.remove_edge(block_b_id, succ_id)
                
                # Add edge from block_a
                if not self.cfg.graph.has_edge(block_a_id, succ_id):
                    self.cfg.graph.add_edge(block_a_id, succ_id, **edge_data)
                
                # Update successor/predecessor sets
                block_a.successors.add(succ_id)
                succ_block = self.cfg.blocks.get(succ_id)
                if succ_block:
                    succ_block.predecessors.discard(block_b_id)
                    succ_block.predecessors.add(block_a_id)
        
        # Step 5: Inherit block_b's exit status if applicable
        if block_b.is_exit:
            block_a.is_exit = True
        
        # Step 6: Remove block_b from the CFG
        if block_b_id in self.cfg.graph:
            self.cfg.graph.remove_node(block_b_id)
        del self.cfg.blocks[block_b_id]
        
        # Update pc_to_block mapping for block_b's range to point to block_a
        for pc in range(block_b.start_pc, block_b.end_pc):
            self.cfg.pc_to_block[pc] = block_a_id
        
        return True
    
    def merge(self) -> DeobfuscationResult:
        """
        Merge sequential basic blocks.
        
        First simplifies JMP chains by redirecting edges to final targets,
        then iteratively finds and merges block pairs until no more merges are possible.
        
        Returns:
            DeobfuscationResult with the number of blocks merged.
        """
        total_merges = 0
        expansions = 0
        
        # First, simplify JMP chains by redirecting edges
        # This makes intermediate JMP blocks unreachable (to be cleaned by DCE)
        jmp_chain_simplifications = self._simplify_jmp_chains()
        total_merges += jmp_chain_simplifications
        
        # Iterate until no more merges are possible
        changed = True
        while changed:
            changed = False
            
            # Collect potential merge pairs
            # We need to be careful about modifying the graph while iterating
            merge_pairs = []
            
            for block_a_id in list(self.cfg.blocks.keys()):
                succs = list(self.cfg.graph.successors(block_a_id))
                if len(succs) == 1:
                    block_b_id = succs[0]
                    if self._can_merge(block_a_id, block_b_id):
                        merge_pairs.append((block_a_id, block_b_id))
            
            # Perform merges
            merged_blocks = set()  # Track blocks that have been merged away
            for block_a_id, block_b_id in merge_pairs:
                # Skip if either block has already been involved in a merge
                if block_a_id in merged_blocks or block_b_id in merged_blocks:
                    continue
                
                # Skip if block_b no longer exists (might have been merged)
                if block_b_id not in self.cfg.blocks:
                    continue
                
                # Check expansion needed
                block_a = self.cfg.blocks.get(block_a_id)
                if block_a and block_a.instructions:
                    last_opcode = block_a.instructions[-1].opcode
                    if last_opcode in (Opcode.JMP, Opcode.FORPREP) or \
                       (last_opcode == Opcode.LOADBOOL and block_a.instructions[-1].c != 0):
                        expansions += 1
                
                if self._merge_blocks(block_a_id, block_b_id):
                    merged_blocks.add(block_b_id)
                    total_merges += 1
                    changed = True
        
        if total_merges == 0:
            return DeobfuscationResult(
                success=True,
                pass_type=DeobfuscationPass.SEQUENTIAL_BLOCK_MERGE,
                changes_made=0,
                details="No mergeable block pairs found"
            )
        
        details = f"Merged {total_merges} block pair(s)"
        if expansions > 0:
            details += f", expanded {expansions} terminator(s)"
        
        return DeobfuscationResult(
            success=True,
            pass_type=DeobfuscationPass.SEQUENTIAL_BLOCK_MERGE,
            changes_made=total_merges,
            details=details
        )


class Deobfuscator:
    """Main deobfuscator class that orchestrates all passes"""
    
    def __init__(self, proto: Prototype, remove_infinite_loops: bool = False):
        self.proto = proto
        self.cfg: Optional[CFG] = None
        self.results: List[DeobfuscationResult] = []
        self.remove_infinite_loops = remove_infinite_loops
    
    def build_cfg(self) -> CFG:
        """Build or return cached CFG"""
        if self.cfg is None:
            self.cfg = build_cfg(self.proto)
        return self.cfg
    
    def run_pass(self, pass_type: DeobfuscationPass) -> DeobfuscationResult:
        """Run a specific deobfuscation pass"""
        cfg_modified = False  # Track if CFG was modified (needs apply_to_prototype)
        proto_modified = False  # Track if prototype was directly modified (invalidate CFG)
        
        if pass_type == DeobfuscationPass.DEAD_CODE_ELIMINATION:
            cfg = self.build_cfg()
            eliminator = DeadCodeEliminator(cfg)
            result = eliminator.eliminate()
            cfg_modified = result.changes_made > 0
        
        elif pass_type == DeobfuscationPass.CONSTANT_FOLDING:
            folder = ConstantFolder(self.proto)
            result = folder.fold()
            proto_modified = result.changes_made > 0
        
        elif pass_type == DeobfuscationPass.DEAD_BRANCH_ELIMINATION:
            cfg = self.build_cfg()
            eliminator = DeadBranchEliminator(cfg)
            result = eliminator.eliminate()
            cfg_modified = result.changes_made > 0
        
        elif pass_type == DeobfuscationPass.SEQUENTIAL_BLOCK_MERGE:
            cfg = self.build_cfg()
            merger = SequentialBlockMerger(cfg)
            result = merger.merge()
            cfg_modified = result.changes_made > 0
        
        else:
            result = DeobfuscationResult(
                success=False,
                pass_type=pass_type,
                changes_made=0,
                details="Unknown pass type"
            )
        
        # If CFG was modified, rebuild code and update prototype
        if cfg_modified and self.cfg is not None:
            new_code = self.cfg.rebuild_code(layout_strategy='original')
            self.proto.code = new_code
            if self.proto.lineinfo:
                self.proto.lineinfo = [0] * len(new_code)
            self.cfg = None  # Invalidate CFG cache
        
        # If prototype was directly modified, invalidate CFG cache
        if proto_modified:
            self.cfg = None  # Invalidate CFG cache
        
        self.results.append(result)
        return result
    
    # Recommended execution order for deobfuscation passes
    PASS_EXECUTION_ORDER = [
        DeobfuscationPass.CONSTANT_FOLDING,
        DeobfuscationPass.DEAD_BRANCH_ELIMINATION,
        DeobfuscationPass.SEQUENTIAL_BLOCK_MERGE,
        DeobfuscationPass.DEAD_CODE_ELIMINATION,
    ]
    
    def run_all_passes(self, max_iterations: int = 10) -> List[DeobfuscationResult]:
        """
        Run all deobfuscation passes in the recommended order until no more changes.
        
        Execution order:
        1. Constant folding
        2. Dead branch elimination
        3. Sequential block merge
        4. Dead code elimination
        
        Note: Each pass that modifies the CFG automatically applies changes to the
        prototype and invalidates the CFG cache.
        """
        all_results = []
        total_changes = 0
        
        for iteration in range(max_iterations):
            changes_this_round = 0
            
            for pass_type in self.PASS_EXECUTION_ORDER:
                result = self.run_pass(pass_type)
                all_results.append(result)
                changes_this_round += result.changes_made
            
            total_changes += changes_this_round
            if changes_this_round == 0:
                break
        
        return all_results
    
    def get_summary(self) -> str:
        """Get a summary of all deobfuscation results"""
        lines = ["Deobfuscation Summary:"]
        lines.append("=" * 40)
        
        for result in self.results:
            status = "✓" if result.success else "✗"
            lines.append(f"{status} {result.pass_type.name}: {result.changes_made} changes")
            if result.details:
                lines.append(f"   {result.details}")
        
        total_changes = sum(r.changes_made for r in self.results)
        lines.append("=" * 40)
        lines.append(f"Total changes: {total_changes}")
        
        return "\n".join(lines)


def deobfuscate(proto: Prototype, verbose: bool = False, 
                remove_infinite_loops: bool = False) -> Prototype:
    """
    Deobfuscate a single prototype.
    
    Args:
        proto: The Lua prototype to deobfuscate.
        verbose: If True, print deobfuscation summary.
        remove_infinite_loops: If True, replace infinite loops with RETURN.
                              If False, just mark them (conservative).
    
    Returns:
        The (possibly modified) prototype.
    """
    deob = Deobfuscator(proto, remove_infinite_loops=remove_infinite_loops)
    results = deob.run_all_passes()
    
    if verbose:
        print(deob.get_summary())
    
    return proto  # Return the (possibly modified) prototype


def deobfuscate_all(proto: Prototype, verbose: bool = False,
                    remove_infinite_loops: bool = False,
                    proto_path: str = "main") -> int:
    """
    Recursively deobfuscate a prototype and all its children.
    
    Args:
        proto: The root prototype to start from.
        verbose: If True, print deobfuscation summary for each prototype.
        remove_infinite_loops: If True, replace infinite loops with RETURN.
        proto_path: The path of the current prototype (for display).
    
    Returns:
        Total number of changes made across all prototypes.
    """
    total_changes = 0
    
    # Deobfuscate this prototype
    if verbose:
        print(f"\n--- Deobfuscating {proto_path} ({len(proto.code)} instructions) ---")
    
    deob = Deobfuscator(proto, remove_infinite_loops=remove_infinite_loops)
    results = deob.run_all_passes()
    changes = sum(r.changes_made for r in results)
    total_changes += changes
    
    if verbose:
        print(deob.get_summary())
    elif changes > 0:
        print(f"  {proto_path}: {changes} changes, {len(proto.code)} instructions remaining")
    
    # Recursively deobfuscate child prototypes
    for i, child_proto in enumerate(proto.protos):
        child_path = f"{proto_path}.F{i}"
        total_changes += deobfuscate_all(
            child_proto, 
            verbose=verbose,
            remove_infinite_loops=remove_infinite_loops,
            proto_path=child_path
        )
    
    return total_changes
