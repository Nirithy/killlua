"""
Lua Bytecode Disassembler

Disassembles Lua bytecode to a human-readable assembly format compatible with 
GameGuardian/LuaAsm style (.lasm format).

Supports:
- Full prototype hierarchy with .func/.end blocks
- Selective closure disassembly (F0, F1, F0/1, etc.)
- .local/.upval/.line directives
- .end local markers
"""

from typing import List, Optional, Set, Tuple, Dict
from dataclasses import dataclass, field

from .parser import Prototype, Instruction, LuaChunk, LuaConstant, parse_file, LocVar, Upvalue
from .opcodes import Opcode, OpMode, ISK, INDEXK, get_opcode_info


def _build_closure_index(proto: Prototype, path: list = None, func_counter: list = None) -> Dict[int, Tuple[Prototype, List[int]]]:
    """
    Build a mapping from global function number (F0, F1, F2...) to (prototype, path).
    
    This mirrors the numbering used by list_closures.
    
    Args:
        proto: The root prototype (main function)
        path: Current path (list of indices)
        func_counter: Global function counter
    
    Returns:
        Dict mapping global function number to (prototype, path)
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


@dataclass
class ClosurePath:
    """
    Represents a path to a specific closure in the prototype tree.
    
    Standard lasm format numbering:
    - main's direct children: 0-based (F0, F1, F2...)
    - nested children: 1-based (F1, F2, F3...)
    
    Internal path uses 0-based indices.
    """
    path: List[int]  # 0-based internal indices
    is_global_number: bool = False  # True if originally parsed as global function number
    global_number: int = -1  # The original global function number if is_global_number is True
    
    @classmethod
    def parse(cls, spec: str) -> 'ClosurePath':
        """
        Parse a closure specification.

        Supports formats:
        1. 'main' - the main function (returns empty path which matches everything)
        2. Global function number: 'F19', '19' (no slashes)
           - Will be resolved to path later with resolve_global_number()
        3. Path notation: 'F0', 'F0/1', 'F0/2/3'
           - First component (direct child of main): 0-based (F0, F1...)
           - Subsequent components (nested): 1-based (F1, F2...)
        """
        if not spec:
            return cls([])

        # Handle 'main' specially
        if spec.lower() == 'main':
            return cls([])

        # Remove 'F' prefix if present
        cleaned = spec.lstrip('Ff')

        if not cleaned:
            return cls([])
        
        # Check if it's a global function number (no path separators)
        if '/' not in cleaned and '-' not in cleaned and ' ' not in cleaned:
            try:
                func_num = int(cleaned)
                # Return a placeholder that needs to be resolved later
                return cls([], is_global_number=True, global_number=func_num)
            except ValueError:
                pass
        
        # Parse path components
        parts = cleaned.replace('/', ' ').replace('-', ' ').split()
        path = []
        for i, part in enumerate(parts):
            try:
                num = int(part)
                if i == 0:
                    # First level: 0-based (user provides F0, F1...)
                    path.append(num)
                else:
                    # Nested levels: 1-based (user provides F1, F2...) → convert to 0-based
                    idx = num - 1
                    if idx >= 0:
                        path.append(idx)
            except ValueError:
                # Handle combined notation
                continue
        
        return cls(path)
    
    def resolve_global_number(self, proto: Prototype) -> 'ClosurePath':
        """
        Resolve a global function number to its path.
        
        Args:
            proto: The root prototype (main function)
        
        Returns:
            A new ClosurePath with the resolved path
        
        Raises:
            ValueError: If the global function number is not found
        """
        if not self.is_global_number:
            return self
        
        # Build closure index
        closure_index = _build_closure_index(proto)
        
        if self.global_number not in closure_index:
            max_num = max(closure_index.keys()) if closure_index else -1
            if max_num >= 0:
                raise ValueError(f"Function F{self.global_number} not found (valid range: F0-F{max_num})")
            else:
                raise ValueError(f"Function F{self.global_number} not found (no child functions)")
        
        _, path = closure_index[self.global_number]
        return ClosurePath(path, is_global_number=False, global_number=-1)
    
    def matches(self, current_path: List[int]) -> bool:
        """Check if the current path matches this specification"""
        if not self.path:
            return True  # Empty path matches everything
        
        # Check if current_path starts with or equals self.path
        if len(current_path) < len(self.path):
            return False
        
        return current_path[:len(self.path)] == self.path
    
    def is_exact_match(self, current_path: List[int]) -> bool:
        """Check if this is an exact match (not just a prefix)"""
        return current_path == self.path
    
    def __str__(self) -> str:
        if not self.path:
            return "main"
        # Display follows lasm format
        parts = []
        for i, idx in enumerate(self.path):
            if i == 0:
                parts.append(str(idx))  # 0-based for first level
            else:
                parts.append(str(idx + 1))  # 1-based for nested
        return "F" + "/".join(parts)


class Disassembler:
    """
    Disassembles Lua bytecode to .lasm format
    
    Output format follows GameGuardian Lua assembler conventions:
    - Header with metadata
    - .source, .linedefined, etc. directives
    - .upval declarations
    - .local declarations inline with code
    - Instructions with .line markers
    - .end local markers
    - .func/.end blocks for child functions
    
    Function numbering uses global counter (same as Java LuaJ implementation):
    - state.func starts at 0
    - Each function's children use offset = state.func, then state.func += n
    - Child i of a function gets number (offset + i)
    """
    
    def __init__(self, chunk: LuaChunk):
        self.chunk = chunk
        self.lines: List[str] = []
        self.indent_level = 0
        self.func_counter = 0  # Global function counter (like Java's state.func)
        
    def disassemble(self, 
                    closure_filter: Optional[str] = None,
                    include_children: bool = True) -> str:
        """
        Disassemble the bytecode to .lasm format
        
        Args:
            closure_filter: Optional closure path filter (e.g., "F0", "F0/1", "F19")
                           Supports both path notation and global function numbers
                           If None, disassemble entire file
            include_children: If True and closure_filter is set, also include child functions
        
        Returns:
            The disassembled code as a string
        """
        self.lines = []
        self.indent_level = 0
        self.func_counter = 0  # Reset counter
        
        # Parse filter
        filter_path = ClosurePath.parse(closure_filter) if closure_filter else None
        
        # Resolve global function number to path if necessary
        if filter_path and filter_path.is_global_number:
            try:
                filter_path = filter_path.resolve_global_number(self.chunk.main)
            except ValueError as e:
                self.emit("; --[=========[ Lua assembler file generated by LuaDeobfuscator")
                self.emit(f"; ERROR: {e}")
                self.emit("; ]=========]")
                return "\n".join(self.lines)
        
        # Header comment
        self.emit("; --[=========[ Lua assembler file generated by LuaDeobfuscator")
        
        # Disassemble main function or filtered closure
        if filter_path and filter_path.path:
            # Navigate to the specified closure and calculate its offset
            proto, actual_path, func_offset, child_counter = self._get_prototype_at_path_with_offset(self.chunk.main, filter_path.path)
            if proto:
                # Set func_counter to the correct value for this closure's children
                self.func_counter = child_counter
                self._disassemble_prototype(proto, func_offset, filter_path, include_children)
            else:
                self.emit(f"; ERROR: Closure path {filter_path} not found")
        else:
            # Disassemble everything starting from main
            self._disassemble_prototype(self.chunk.main, -1, filter_path, include_children)
        
        self.emit("; ]=========]")
        
        return "\n".join(self.lines)
    
    def _get_prototype_at_path(self, proto: Prototype, path: List[int]) -> Tuple[Optional[Prototype], List[int]]:
        """Navigate to a specific prototype given a path"""
        current = proto
        traversed = []
        
        for idx in path:
            if idx >= len(current.protos):
                return None, traversed
            current = current.protos[idx]
            traversed.append(idx)
        
        return current, traversed
    
    def _get_prototype_at_path_with_offset(self, proto: Prototype, path: List[int]) -> Tuple[Optional[Prototype], List[int], int, int]:
        """
        Navigate to a specific prototype and calculate its global function number.

        Uses _build_closure_index to correctly compute the global function number,
        accounting for all descendants of previous siblings.

        Returns:
            (prototype, traversed_path, func_number, func_counter_for_children)
            - func_number: the global function number of the target prototype
            - func_counter_for_children: the func_counter value to use for the target's children
        """
        if not path:
            return proto, [], -1, 0

        # Build closure index to get correct global function numbers
        closure_index = _build_closure_index(proto)

        # Find the global function number for this path
        target_num = -1
        for func_num, (_, func_path) in closure_index.items():
            if func_path == path:
                target_num = func_num
                break

        if target_num < 0:
            return None, [], -1, 0

        # Navigate to the prototype
        current = proto
        traversed = []
        for idx in path:
            if idx >= len(current.protos):
                return None, traversed, -1, 0
            current = current.protos[idx]
            traversed.append(idx)

        # Calculate func_counter for children
        # After disassembling the target, func_counter should be at the point
        # where target's children would start numbering
        # This is: target_num + 1 + number of functions that are descendants of target's previous siblings
        # But we need to count functions that come BEFORE target's first child

        # Find how many functions are in the subtree of target and its previous siblings
        child_counter = target_num + 1

        # Count all functions that are descendants of the target's previous siblings
        # These functions come after target in the global numbering but before target's children
        # Actually, in the closure_index, the numbering goes:
        # - All children at depth=1 numbered first (by DFS order)
        # - Then all children at depth=2, etc.
        # So we need to find where target's children would start

        # The children of target start after all functions that are numbered
        # before target's first child in the DFS traversal

        # Simple approach: count how many functions have paths that would come
        # before target's children's paths in DFS order

        # In the closure_index, children are numbered sequentially.
        # If target is F363, its children start at some offset.
        # We need to find how many functions exist in total before target's
        # first child would be numbered.

        # Find where target's children would start
        # Look for the first path in closure_index that starts with target's path + [0]
        first_child_num = -1
        for func_num, (_, func_path) in sorted(closure_index.items()):
            if len(func_path) == len(path) + 1 and func_path[:len(path)] == path:
                first_child_num = func_num
                break

        if first_child_num >= 0:
            child_counter = first_child_num
        else:
            # Target has no children, counter doesn't matter much
            # But set it to a reasonable value
            child_counter = target_num + 1

        return current, traversed, target_num, child_counter
    
    def emit(self, line: str = ""):
        """Add a line with current indentation"""
        indent = "\t" * self.indent_level
        self.lines.append(indent + line if line else "")
    
    def _disassemble_prototype(self, 
                               proto: Prototype, 
                               func_num: int,
                               filter_path: Optional[ClosurePath],
                               include_children: bool,
                               parent_source: Optional[str] = None):
        """
        Disassemble a single prototype and optionally its children
        
        Args:
            proto: The prototype to disassemble
            func_num: Global function number (-1 for main)
            filter_path: Optional filter for selective disassembly
            include_children: Whether to include child functions
        """
        
        # Determine function name
        is_main = (func_num == -1)
        if is_main:
            # Main function - emit metadata as header comment
            self.emit(f"; {len(proto.upvalues)} upvalues, {len(proto.locvars)} locals, {len(proto.constants)} constants, {len(proto.protos)} funcs")
        else:
            func_name = f"F{func_num}"
            self.emit(f".func {func_name} ; {len(proto.upvalues)} upvalues, {len(proto.locvars)} locals, {len(proto.constants)} constants, {len(proto.protos)} funcs")
            self.indent_level += 1
        
        # Source (fallback to parent source if missing)
        source_to_emit = proto.source or parent_source
        if source_to_emit:
            self.emit(f'.source "{source_to_emit}"')
        
        # Function metadata
        self.emit(f".linedefined {proto.line_defined}")
        self.emit(f".lastlinedefined {proto.last_line_defined}")
        self.emit(f".numparams {proto.num_params}")
        self.emit(f".is_vararg {proto.is_vararg}")
        self.emit(f".maxstacksize {proto.max_stack_size}")
        self.emit()
        
        # Upvalues
        for i, upval in enumerate(proto.upvalues):
            upval_name = upval.name if upval.name else f"u{i}"
            # Format: .upval v0 "_ENV" ; u0 or .upval u0 "_ENV" ; u0
            if upval.instack:
                self.emit(f'.upval v{upval.idx} "{upval_name}" ; u{i}')
            else:
                self.emit(f'.upval u{upval.idx} "{upval_name}" ; u{i}')
        
        if proto.upvalues:
            self.emit()
        
        # Build local variable map: pc -> list of locals that start at this pc
        local_starts = {}  # pc -> list of (slot, name)
        local_ends = {}    # pc -> list of (slot, name)
        
        for locvar in proto.locvars:
            if locvar.varname:
                start_pc = locvar.startpc
                end_pc = locvar.endpc
                
                # Find the slot (register) for this local - approximate by order
                slot = proto.locvars.index(locvar)
                
                if start_pc not in local_starts:
                    local_starts[start_pc] = []
                local_starts[start_pc].append((slot, locvar.varname))
                
                if end_pc not in local_ends:
                    local_ends[end_pc] = []
                local_ends[end_pc].append((slot, locvar.varname))
        
        # Calculate offset for CLOSURE instructions
        # At this point, func_counter is already at the value before this function's children
        closure_offset = self.func_counter
        
        # Pre-scan instructions to find jump targets and generate labels
        jump_targets = self._collect_jump_targets(proto)
        
        # Disassemble instructions
        last_line = -1
        skip_next = False  # Flag to skip next instruction (used by SETLIST C=0)
        for pc, instr in enumerate(proto.code):
            # Skip this instruction if it's data for the previous SETLIST
            if skip_next:
                skip_next = False
                continue
            
            # Check for local variable declarations at this PC
            if pc in local_starts:
                for slot, name in local_starts[pc]:
                    self.emit(f'.local v{slot} "{name}"')
            
            # Emit jump target label if this PC is a jump target
            if pc in jump_targets:
                self.emit(f":goto_{pc}")
            
            # Line number directive
            if pc < len(proto.lineinfo):
                line = proto.lineinfo[pc]
                if line != last_line and line > 0:
                    self.emit(f".line {line}")
                    last_line = line
            
            # Check if this is SETLIST with C=0 (next instruction is data)
            if instr.opcode == Opcode.SETLIST and instr.c == 0:
                # Read the actual block number from next instruction
                if pc + 1 < len(proto.code):
                    next_raw = proto.code[pc + 1]
                    # The entire next instruction word is the block number (as EXTRAARG format: Ax)
                    block_num = next_raw.ax if hasattr(next_raw, 'ax') else (next_raw.raw >> 6)
                    instr_str = f"SETLIST v{instr.a}..v{instr.a + instr.b} {block_num} ; uses EXTRAARG"
                    skip_next = True  # Skip the next instruction (it's data)
                else:
                    instr_str = self._format_instruction(instr, proto, pc, closure_offset)
            else:
                # Instruction (pass closure_offset for CLOSURE numbering, and jump_targets for label formatting)
                instr_str = self._format_instruction(instr, proto, pc, closure_offset, jump_targets)
            self.emit(instr_str)
            # Reference output uses a blank line after each instruction
            self.emit()
        
        # End local markers
        for locvar in proto.locvars:
            if locvar.varname:
                slot = proto.locvars.index(locvar)
                self.emit(f'.end local v{slot} "{locvar.varname}"')
        
        if proto.locvars:
            self.emit()
        
        # Child prototypes (like Java's printFunction logic)
        if include_children and proto.protos:
            n = len(proto.protos)
            offset = self.func_counter
            self.func_counter += n  # Pre-increment like Java
            
            for i, child in enumerate(proto.protos):
                child_func_num = offset + i
                self._disassemble_prototype(child, child_func_num, filter_path, include_children, source_to_emit)
        
        # End function
        if not is_main:
            self.indent_level -= 1
            func_name = f"F{func_num}"
            self.emit(f".end ; {func_name}")
            self.emit()
    
    def _collect_jump_targets(self, proto: Prototype) -> Set[int]:
        """
        Pre-scan instructions to collect all jump target PCs.
        
        Returns:
            Set of PC values that are jump targets
        """
        targets = set()
        
        for pc, instr in enumerate(proto.code):
            try:
                op = Opcode(instr.opcode)
            except ValueError:
                continue
            
            # Check for jump instructions
            if op == Opcode.JMP:
                target = pc + instr.sbx + 1
                targets.add(target)
            elif op in (Opcode.FORLOOP, Opcode.FORPREP, Opcode.TFORLOOP):
                target = pc + instr.sbx + 1
                targets.add(target)
            # Conditional jumps (EQ, LT, LE, TEST, TESTSET) don't have a direct target,
            # they are followed by a JMP instruction which will be handled above
        
        return targets
    
    def _format_instruction(self, instr: Instruction, proto: Prototype, pc: int, closure_offset: int = 0, jump_targets: Set[int] = None) -> str:
        """
        Format a single instruction to .lasm format
        
        Args:
            instr: The instruction to format
            proto: The containing prototype
            pc: Program counter
            closure_offset: Global offset for CLOSURE instruction numbering
            jump_targets: Set of PCs that are jump targets (for label formatting)
        """
        if jump_targets is None:
            jump_targets = set()
        
        opcode = instr.opcode
        name = instr.opcode_name
        
        # Get RK formatter
        def rk(val: int) -> str:
            """Format a register/constant reference"""
            if ISK(val):
                k_idx = INDEXK(val)
                if k_idx < len(proto.constants):
                    return self._format_constant(proto.constants[k_idx])
                return f"K{k_idx}"
            return f"v{val}"
        
        def reg(r: int) -> str:
            """Format register reference"""
            return f"v{r}"
        
        def upval(u: int) -> str:
            """Format upvalue reference"""
            return f"u{u}"
        
        # Format based on opcode
        try:
            op = Opcode(opcode)
        except ValueError:
            return f"UNKNOWN_{opcode} {instr.a} {instr.b} {instr.c}"
        
        # Instruction formatting based on opcode type
        if op == Opcode.MOVE:
            return f"MOVE {reg(instr.a)} {reg(instr.b)}"
        
        elif op == Opcode.LOADK:
            const_str = self._format_constant(proto.constants[instr.bx]) if instr.bx < len(proto.constants) else f"K{instr.bx}"
            return f"LOADK {reg(instr.a)} {const_str}"
        
        elif op == Opcode.LOADKX:
            return f"LOADKX {reg(instr.a)}"
        
        elif op == Opcode.LOADBOOL:
            return f"LOADBOOL {reg(instr.a)} {instr.b} {instr.c}"
        
        elif op == Opcode.LOADNIL:
            if instr.b == 0:
                return f"LOADNIL {reg(instr.a)}"
            return f"LOADNIL {reg(instr.a)}..{reg(instr.a + instr.b)}"
        
        elif op == Opcode.GETUPVAL:
            return f"GETUPVAL {reg(instr.a)} {upval(instr.b)}"
        
        elif op == Opcode.GETTABUP:
            return f"GETTABUP {reg(instr.a)} {upval(instr.b)} {rk(instr.c)}"
        
        elif op == Opcode.GETTABLE:
            return f"GETTABLE {reg(instr.a)} {reg(instr.b)} {rk(instr.c)}"
        
        elif op == Opcode.SETTABUP:
            return f"SETTABUP {upval(instr.a)} {rk(instr.b)} {rk(instr.c)}"
        
        elif op == Opcode.SETUPVAL:
            return f"SETUPVAL {reg(instr.a)} {upval(instr.b)}"
        
        elif op == Opcode.SETTABLE:
            return f"SETTABLE {reg(instr.a)} {rk(instr.b)} {rk(instr.c)}"
        
        elif op == Opcode.NEWTABLE:
            # Decode array and hash sizes from FPF encoding
            arr_size = instr.b
            hash_size = instr.c
            return f"NEWTABLE {reg(instr.a)} {arr_size} {hash_size}"
        
        elif op == Opcode.SELF:
            return f"SELF {reg(instr.a)} {reg(instr.b)} {rk(instr.c)}"
        
        elif op in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV, 
                   Opcode.MOD, Opcode.POW, Opcode.IDIV):
            return f"{name} {reg(instr.a)} {rk(instr.b)} {rk(instr.c)}"
        
        elif op in (Opcode.BAND, Opcode.BOR, Opcode.BXOR, Opcode.SHL, Opcode.SHR):
            return f"{name} {reg(instr.a)} {rk(instr.b)} {rk(instr.c)}"
        
        elif op == Opcode.UNM:
            return f"UNM {reg(instr.a)} {reg(instr.b)}"
        
        elif op == Opcode.BNOT:
            return f"BNOT {reg(instr.a)} {reg(instr.b)}"
        
        elif op == Opcode.NOT:
            return f"NOT {reg(instr.a)} {reg(instr.b)}"
        
        elif op == Opcode.LEN:
            return f"LEN {reg(instr.a)} {reg(instr.b)}"
        
        elif op == Opcode.CONCAT:
            return f"CONCAT {reg(instr.a)} {reg(instr.b)} {reg(instr.c)}"
        
        elif op == Opcode.JMP:
            target = pc + instr.sbx + 1
            offset = instr.sbx
            arrow = "↓" if offset >= 0 else "↑"
            if instr.a == 0:
                return f"JMP :goto_{target}  ; {offset:+d} {arrow}"
            return f"JMP {instr.a} :goto_{target}  ; {offset:+d} {arrow}"
        
        elif op in (Opcode.EQ, Opcode.LT, Opcode.LE, Opcode.NEQ, Opcode.GE, Opcode.GT):
            return f"{name} {instr.a} {rk(instr.b)} {rk(instr.c)}"
        
        elif op == Opcode.TEST:
            return f"TEST {reg(instr.a)} {instr.c}"
        
        elif op == Opcode.TESTSET:
            return f"TESTSET {reg(instr.a)} {reg(instr.b)} {instr.c}"
        
        elif op == Opcode.CALL:
            # B: 0 = vararg, 1 = no args, n = n-1 args
            # C: 0 = set_top, 1 = no returns, n = n-1 returns
            if instr.b == 0:
                arg_range = "..TOP"
            elif instr.b == 1:
                arg_range = ""
            else:
                arg_range = f"..{reg(instr.a + instr.b - 1)}"

            if instr.c == 0:
                ret_part = "SET_TOP"
            elif instr.c == 1:
                ret_part = ""
            else:
                ret_part = f"{reg(instr.a)}..{reg(instr.a + instr.c - 2)}"

            # LuaJ Print collapses the common pattern (B=0,C=1) to just CALL vA
            suppress_arg_range = (instr.b == 0 and instr.c == 1)

            call_part = f"CALL {reg(instr.a)}"
            if arg_range and not suppress_arg_range:
                call_part += arg_range

            if ret_part:
                return f"{call_part} {ret_part}"
            return call_part
        
        elif op == Opcode.TAILCALL:
            if instr.b == 0:
                return f"TAILCALL {reg(instr.a)}..TOP"
            elif instr.b == 1:
                return f"TAILCALL {reg(instr.a)}"
            else:
                return f"TAILCALL {reg(instr.a)}..{reg(instr.a + instr.b - 1)}"
        
        elif op == Opcode.RETURN:
            # LuaJ print style: B=0 (varret) still shows the first register only
            if instr.b == 0:
                return f"RETURN {reg(instr.a)}"
            elif instr.b == 1:
                return "RETURN "
            elif instr.b == 2:
                return f"RETURN {reg(instr.a)}"
            else:
                return f"RETURN {reg(instr.a)}..{reg(instr.a + instr.b - 2)}"
        
        elif op == Opcode.FORLOOP:
            target = pc + instr.sbx + 1
            offset = instr.sbx
            arrow = "↓" if offset >= 0 else "↑"
            return f"FORLOOP {reg(instr.a)} :goto_{target}  ; {offset:+d} {arrow}"
        
        elif op == Opcode.FORPREP:
            target = pc + instr.sbx + 1
            offset = instr.sbx
            arrow = "↓" if offset >= 0 else "↑"
            return f"FORPREP {reg(instr.a)} :goto_{target}  ; {offset:+d} {arrow}"
        
        elif op == Opcode.TFORCALL:
            # TFORCALL A C: R(A+3), ..., R(A+2+C) := R(A)(R(A+1), R(A+2))
            # Format: TFORCALL vA..v(A+2+C)
            end_reg = instr.a + 2 + instr.c
            return f"TFORCALL {reg(instr.a)}..{reg(end_reg)}"
        
        elif op == Opcode.TFORLOOP:
            target = pc + instr.sbx + 1
            offset = instr.sbx
            arrow = "↓" if offset >= 0 else "↑"
            return f"TFORLOOP {reg(instr.a)} :goto_{target}  ; {offset:+d} {arrow}"
        
        elif op == Opcode.SETLIST:
            if instr.c == 0:
                # Next instruction contains the block number
                return f"SETLIST {reg(instr.a)}..{reg(instr.a + instr.b)} 0"
            else:
                return f"SETLIST {reg(instr.a)}..{reg(instr.a + instr.b)} {instr.c}"
        
        elif op == Opcode.CLOSURE:
            # CLOSURE numbering uses global counter offset
            # Like Java: bx + state.func (where state.func is the offset for this function's children)
            func_num = closure_offset + instr.bx
            return f"CLOSURE {reg(instr.a)} F{func_num}"
        
        elif op == Opcode.VARARG:
            if instr.b == 0:
                return f"VARARG {reg(instr.a)}..TOP"
            elif instr.b == 1:
                return f"VARARG"
            else:
                return f"VARARG {reg(instr.a)}..{reg(instr.a + instr.b - 2)}"
        
        elif op == Opcode.EXTRAARG:
            return f"EXTRAARG {instr.ax}"
        
        # Custom LuaJ opcodes
        elif op == Opcode.GETFIELDU:
            return f"GETFIELDU {reg(instr.a)} {upval(instr.b)} {rk(instr.c)}"
        
        elif op == Opcode.GETFIELDT:
            return f"GETFIELDT {reg(instr.a)} {reg(instr.b)} {rk(instr.c)}"
        
        elif op == Opcode.CLASS:
            return f"CLASS {reg(instr.a)} {instr.b} {instr.c}"
        
        elif op == Opcode.OR:
            return f"OR {reg(instr.a)} {rk(instr.b)} {rk(instr.c)}"
        
        elif op == Opcode.AND:
            return f"AND {reg(instr.a)} {rk(instr.b)} {rk(instr.c)}"
        
        else:
            # Generic format
            info = get_opcode_info(opcode)
            if info:
                if info.mode == OpMode.iABC:
                    return f"{name} {reg(instr.a)} {instr.b} {instr.c}"
                elif info.mode == OpMode.iABx:
                    return f"{name} {reg(instr.a)} {instr.bx}"
                elif info.mode == OpMode.iAsBx:
                    return f"{name} {reg(instr.a)} {instr.sbx:+d}"
                elif info.mode == OpMode.iAx:
                    return f"{name} {instr.ax}"
            return f"{name} {instr.a} {instr.b} {instr.c}"
    
    def _format_constant(self, const: LuaConstant) -> str:
        """Format a constant value for display"""
        from .parser import LuaConstantType
        import math
        
        if const.type == LuaConstantType.NIL:
            return "nil"
        elif const.type == LuaConstantType.BOOLEAN:
            return "true" if const.value else "false"
        elif const.type == LuaConstantType.STRING:
            # Escape special characters
            s = const.value
            s = s.replace('\\', '\\\\')
            s = s.replace('"', '\\"')
            s = s.replace('\n', '\\n')
            s = s.replace('\r', '\\r')
            s = s.replace('\t', '\\t')
            return f'"{s}"'
        elif const.type == LuaConstantType.NUMBER:
            # Format number
            if math.isnan(const.value):
                return "nan"
            elif math.isinf(const.value):
                return "inf" if const.value > 0 else "-inf"
            elif const.value == int(const.value):
                return str(int(const.value))
            return str(const.value)
        elif const.type == LuaConstantType.INT:
            return str(const.value)
        elif const.type == LuaConstantType.BIGNUMBER:
            return str(const.value)
        else:
            return str(const.value)


def disassemble_file(filepath: str, 
                     closure_filter: Optional[str] = None,
                     include_children: bool = True) -> str:
    """
    Disassemble a Lua bytecode file
    
    Args:
        filepath: Path to the .luac file
        closure_filter: Optional closure filter (e.g., "F0", "F0/1")
        include_children: Whether to include child functions
    
    Returns:
        Disassembled code as a string
    """
    chunk = parse_file(filepath)
    disasm = Disassembler(chunk)
    return disasm.disassemble(closure_filter, include_children)


def disassemble_prototype(proto: Prototype, 
                          chunk: LuaChunk = None,
                          closure_filter: Optional[str] = None) -> str:
    """
    Disassemble a specific prototype
    
    Args:
        proto: The prototype to disassemble
        chunk: Optional LuaChunk for context
        closure_filter: Optional closure filter
    
    Returns:
        Disassembled code as a string
    """
    if chunk is None:
        # Create a minimal chunk
        from .parser import LuaHeader
        header = LuaHeader(
            signature=b'\x1bLua',
            version=0x52,
            format=0,
            endianness=1,
            size_int=4,
            size_size_t=4,
            size_instruction=4,
            size_lua_number=8,
            integral_flag=0,
            tail=b'\x19\x93\r\n\x1a\n'
        )
        chunk = LuaChunk(header=header, main=proto)
    
    disasm = Disassembler(chunk)
    return disasm.disassemble(closure_filter)


def list_closures(proto: Prototype, path: List[int] = None, func_counter: List[int] = None) -> List[Tuple[str, str, Prototype]]:
    """
    List all closures in a prototype tree
    
    Uses global counter for display names (like Java's state.func), 
    and path notation for CLI selectors.
    
    Returns:
        List of (display_name, cli_selector, prototype) tuples
        - display_name: Global numbering like lasm output (F0, F1, F2...)
        - cli_selector: Path notation for CLI -c option (F0, F0/1, F0/2...)
    """
    if path is None:
        path = []
    if func_counter is None:
        func_counter = [0]  # Use list to allow modification in nested calls
    
    result = []
    
    if not path:
        result.append(("main", "main", proto))
    else:
        # CLI selector uses path notation
        parts = []
        for i, idx in enumerate(path):
            if i == 0:
                parts.append(str(idx))
            else:
                parts.append(str(idx + 1))
        cli_selector = "F" + "/".join(parts)
        
        # Display name uses the global counter (calculated when parent adds us)
        # This is passed as part of the path processing
        display_name = f"F{path[-1]}" if len(path) == 1 else cli_selector
        result.append((display_name, cli_selector, proto))
    
    # Process children with global counter
    if proto.protos:
        n = len(proto.protos)
        offset = func_counter[0]
        func_counter[0] += n
        
        for i, child in enumerate(proto.protos):
            child_path = path + [i]
            child_func_num = offset + i
            
            # Generate CLI selector
            if not path:
                cli_sel = f"F{i}"
            else:
                parts = []
                for j, idx in enumerate(path):
                    if j == 0:
                        parts.append(str(idx))
                    else:
                        parts.append(str(idx + 1))
                parts.append(str(i + 1))  # Nested level uses 1-based
                cli_sel = "F" + "/".join(parts)
            
            display_name = f"F{child_func_num}"
            result.append((display_name, cli_sel, child))
            
            # Recursively process grandchildren
            for gc in list_closures_children(child, child_path, func_counter):
                result.append(gc)
    
    return result


def list_closures_children(proto: Prototype, path: List[int], func_counter: List[int]) -> List[Tuple[str, str, Prototype]]:
    """Helper function to list closures of children (not including the proto itself)"""
    result = []
    
    if proto.protos:
        n = len(proto.protos)
        offset = func_counter[0]
        func_counter[0] += n
        
        for i, child in enumerate(proto.protos):
            child_path = path + [i]
            child_func_num = offset + i
            
            # Generate CLI selector
            parts = []
            for j, idx in enumerate(path):
                if j == 0:
                    parts.append(str(idx))
                else:
                    parts.append(str(idx + 1))
            parts.append(str(i + 1))
            cli_sel = "F" + "/".join(parts)
            
            display_name = f"F{child_func_num}"
            result.append((display_name, cli_sel, child))
            
            # Recursively process grandchildren
            result.extend(list_closures_children(child, child_path, func_counter))
    
    return result
