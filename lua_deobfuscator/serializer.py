"""
Lua Bytecode Serializer

Serializes LuaChunk objects back to binary Lua bytecode format.
Designed to be symmetric with parser.py.

Based on the specification from requirements_serializer.md
"""

from typing import List, Optional, Dict
import struct

from .parser import (
    LuaChunk, LuaHeader, Prototype, Instruction, LuaConstant, 
    Upvalue, LocVar, LuaConstantType
)
from .opcodes import OpMode, get_opcode_mode, MAXARG_sBx


class LuaBytecodeSerializer:
    """
    Serializes LuaChunk objects to binary Lua bytecode.
    
    Symmetric with LuaBytecodeParser - whatever the parser reads,
    this serializer writes in the exact same format.
    """
    
    # Default header values (matching parser.py)
    LUA_SIGNATURE = b'\x1bLua'
    LUA_VERSION = 0x52  # Lua 5.2
    LUAC_FORMAT = 0x00
    LUAC_TAIL = b'\x19\x93\r\n\x1a\n'
    
    def __init__(self, chunk: LuaChunk):
        """
        Initialize the serializer with a LuaChunk.
        
        Args:
            chunk: The LuaChunk to serialize
        """
        self.chunk = chunk
        self.buffer = bytearray()
        
        # Read configuration from header
        self.little_endian = (chunk.header.endianness == 1)
        self.size_int = chunk.header.size_int
        self.size_size_t = chunk.header.size_size_t
        self.size_instruction = chunk.header.size_instruction
        self.size_lua_number = chunk.header.size_lua_number
        self.integral_flag = chunk.header.integral_flag
    
    # ============== Basic Write Methods ==============
    
    def write_byte(self, value: int) -> None:
        """Write a single byte"""
        self.buffer.append(value & 0xFF)
    
    def write_bytes(self, data: bytes) -> None:
        """Write raw bytes"""
        self.buffer.extend(data)
    
    def write_int(self, value: int) -> None:
        """Write a signed size_int integer"""
        byte_order = 'little' if self.little_endian else 'big'
        self.buffer.extend(value.to_bytes(self.size_int, byte_order, signed=True))
    
    def write_uint(self, value: int) -> None:
        """Write an unsigned size_int integer"""
        byte_order = 'little' if self.little_endian else 'big'
        self.buffer.extend(value.to_bytes(self.size_int, byte_order, signed=False))
    
    def write_size_t(self, value: int) -> None:
        """Write a size_t value"""
        byte_order = 'little' if self.little_endian else 'big'
        self.buffer.extend(value.to_bytes(self.size_size_t, byte_order, signed=False))
    
    def write_number(self, value: float) -> None:
        """Write a Lua number (double or float)"""
        if self.size_lua_number == 8:
            fmt = '<d' if self.little_endian else '>d'
        else:
            fmt = '<f' if self.little_endian else '>f'
        self.buffer.extend(struct.pack(fmt, value))
    
    def write_string(self, value: Optional[str]) -> None:
        """
        Write a Lua string (size + data + null terminator)
        
        Format:
        - If value is None: size_t = 0 (no data follows)
        - Otherwise: size_t = len + 1, followed by data and null byte
        
        First tries UTF-8 encoding for proper Unicode support.
        Falls back to latin-1 to preserve byte values exactly if UTF-8 
        results in different bytes. This matches the parser's behavior.
        """
        if value is None:
            self.write_size_t(0)
        else:
            # Try UTF-8 first for proper Unicode support (matching parser)
            try:
                encoded = value.encode('utf-8')
            except UnicodeEncodeError:
                # Fall back to latin-1 for 1:1 byte mapping
                encoded = value.encode('latin-1')
            # Size includes null terminator
            self.write_size_t(len(encoded) + 1)
            self.buffer.extend(encoded)
            self.write_byte(0)  # Null terminator
    
    def write_instruction(self, value: int) -> None:
        """Write a single instruction (32-bit)"""
        byte_order = 'little' if self.little_endian else 'big'
        self.buffer.extend(value.to_bytes(4, byte_order, signed=False))
    
    # ============== Instruction Encoding ==============
    
    @staticmethod
    def encode_instruction(instr: Instruction) -> int:
        """
        Encode an Instruction object to a 32-bit integer.
        
        Args:
            instr: The Instruction object to encode
            
        Returns:
            32-bit unsigned integer representation
        """
        mode = get_opcode_mode(instr.opcode)
        
        if mode == OpMode.iABC:
            return ((instr.opcode & 0x3F) |
                    ((instr.a & 0xFF) << 6) |
                    ((instr.c & 0x1FF) << 14) |
                    ((instr.b & 0x1FF) << 23))
        
        elif mode == OpMode.iABx:
            return ((instr.opcode & 0x3F) |
                    ((instr.a & 0xFF) << 6) |
                    ((instr.bx & 0x3FFFF) << 14))
        
        elif mode == OpMode.iAsBx:
            # Convert signed sBx to unsigned representation
            sbx_encoded = instr.sbx + MAXARG_sBx  # Add 131071
            return ((instr.opcode & 0x3F) |
                    ((instr.a & 0xFF) << 6) |
                    ((sbx_encoded & 0x3FFFF) << 14))
        
        elif mode == OpMode.iAx:
            return ((instr.opcode & 0x3F) |
                    ((instr.ax & 0x3FFFFFF) << 6))
        
        else:
            raise ValueError(f"Unknown instruction mode: {mode}")
    
    # ============== High-Level Serialization Methods ==============
    
    def serialize_header(self) -> None:
        """Serialize the Lua bytecode header"""
        header = self.chunk.header
        
        # Signature
        self.write_bytes(header.signature)
        
        # Version and format
        self.write_byte(header.version)
        self.write_byte(header.format)
        
        # Endianness
        self.write_byte(header.endianness)
        
        # Size configuration
        self.write_byte(header.size_int)
        self.write_byte(header.size_size_t)
        self.write_byte(header.size_instruction)
        self.write_byte(header.size_lua_number)
        self.write_byte(header.integral_flag)
        
        # Tail marker
        self.write_bytes(header.tail)
    
    def serialize_constants(self, constants: List[LuaConstant]) -> None:
        """Serialize the constants array"""
        self.write_uint(len(constants))
        
        for const in constants:
            # Write type byte
            self.write_byte(const.type.value if isinstance(const.type, LuaConstantType) else const.type)
            
            if const.type == LuaConstantType.NIL:
                # No data for nil
                pass
            
            elif const.type == LuaConstantType.BOOLEAN:
                self.write_byte(1 if const.value else 0)
            
            elif const.type == LuaConstantType.BIGNUMBER:
                # Big number stored as string
                self.write_string(const.value)
            
            elif const.type == LuaConstantType.NUMBER:
                self.write_number(const.value)
            
            elif const.type == LuaConstantType.STRING:
                self.write_string(const.value)
            
            elif const.type == LuaConstantType.INT:
                # LUA_TINT uses 4-byte integer
                # Handle values that may exceed signed 32-bit range
                value = const.value
                # If value is too large for signed int, convert to unsigned representation
                if value > 2147483647:
                    # This is a large unsigned value stored as signed
                    # We need to write it as the two's complement representation
                    value = value - 0x100000000  # Convert to negative for signed representation
                self.write_int(value)
            
            else:
                raise ValueError(f"Unknown constant type: {const.type}")
    
    def serialize_upvalues(self, upvalues: List[Upvalue]) -> None:
        """Serialize upvalue descriptors (without names)"""
        self.write_uint(len(upvalues))
        
        for upval in upvalues:
            self.write_byte(1 if upval.instack else 0)
            self.write_byte(upval.idx)
    
    def serialize_debug_info(self, proto: Prototype) -> None:
        """
        Serialize debug information.
        
        Order: source, lineinfo, locvars, upvalue names
        (matches parser.parse_debug_info)
        
        Note: The upvalue names count can be less than the total upvalues
        count when debug info is stripped. We only write names for upvalues
        that have them (non-None names).
        """
        # Source name
        self.write_string(proto.source)
        
        # Line info
        self.write_uint(len(proto.lineinfo))
        for line in proto.lineinfo:
            self.write_int(line)
        
        # Local variables
        self.write_uint(len(proto.locvars))
        for locvar in proto.locvars:
            self.write_string(locvar.varname)
            self.write_uint(locvar.startpc)
            self.write_uint(locvar.endpc)
        
        # Upvalue names - only count those that have names
        # When debug info is stripped, upvalues exist but have no names
        # We need to write the count of named upvalues, not total upvalues
        # 
        # The parser reads n names and assigns them to the first n upvalues.
        # So we need to count how many consecutive upvalues from the start
        # have names, and only write those.
        named_count = 0
        for upval in proto.upvalues:
            if upval.name is not None:
                named_count += 1
            else:
                # Stop at first None - names must be consecutive from start
                break
        
        self.write_uint(named_count)
        for i in range(named_count):
            self.write_string(proto.upvalues[i].name)
    
    def serialize_prototype(self, proto: Prototype) -> None:
        """
        Recursively serialize a function prototype.
        
        Order matches parser.parse_prototype:
        1. Function metadata (line_defined, num_params, etc.)
        2. Code (instructions)
        3. Constants
        4. Child prototypes (recursive)
        5. Upvalues
        6. Debug info
        """
        # Function metadata
        self.write_uint(proto.line_defined)
        self.write_uint(proto.last_line_defined)
        self.write_byte(proto.num_params)
        self.write_byte(proto.is_vararg)
        self.write_byte(proto.max_stack_size)
        
        # Code (instructions)
        self.write_uint(len(proto.code))
        for instr in proto.code:
            # Use raw value if available, otherwise encode
            if hasattr(instr, 'raw') and instr.raw is not None:
                self.write_instruction(instr.raw)
            else:
                encoded = self.encode_instruction(instr)
                self.write_instruction(encoded)
        
        # Constants
        self.serialize_constants(proto.constants)
        
        # Child prototypes (recursive)
        self.write_uint(len(proto.protos))
        for child in proto.protos:
            self.serialize_prototype(child)
        
        # Upvalues (descriptors only)
        self.serialize_upvalues(proto.upvalues)
        
        # Debug info (source, lineinfo, locvars, upvalue names)
        self.serialize_debug_info(proto)
    
    def serialize(self) -> bytes:
        """
        Serialize the complete LuaChunk to bytes.
        
        Returns:
            bytes: The serialized Lua bytecode
        """
        self.buffer.clear()
        
        # Serialize header
        self.serialize_header()
        
        # Serialize main prototype
        self.serialize_prototype(self.chunk.main)
        
        return bytes(self.buffer)


# ============== Public API ==============

def serialize_chunk(chunk: LuaChunk) -> bytes:
    """
    Serialize a LuaChunk to bytes.
    
    Args:
        chunk: The LuaChunk to serialize
        
    Returns:
        bytes: The serialized Lua bytecode
    """
    serializer = LuaBytecodeSerializer(chunk)
    return serializer.serialize()


def serialize_file(chunk: LuaChunk, filepath: str) -> None:
    """
    Serialize a LuaChunk and write to a file.
    
    Args:
        chunk: The LuaChunk to serialize
        filepath: Path to the output file
    """
    data = serialize_chunk(chunk)
    with open(filepath, 'wb') as f:
        f.write(data)


def create_default_header() -> LuaHeader:
    """
    Create a default Lua 5.2 header.
    
    Returns:
        LuaHeader: A header with standard Lua 5.2 values
    """
    return LuaHeader(
        signature=b'\x1bLua',
        version=0x52,
        format=0x00,
        endianness=0x01,  # Little endian
        size_int=4,
        size_size_t=4,
        size_instruction=4,
        size_lua_number=8,
        integral_flag=0x00,
        tail=b'\x19\x93\r\n\x1a\n'
    )


def chunk_from_prototype(proto: Prototype, header: Optional[LuaHeader] = None) -> LuaChunk:
    """
    Create a LuaChunk from a Prototype using a default or provided header.
    
    Args:
        proto: The main Prototype
        header: Optional header (uses default if not provided)
        
    Returns:
        LuaChunk: A complete LuaChunk ready for serialization
    """
    if header is None:
        header = create_default_header()
    return LuaChunk(header=header, main=proto)


# ============== Jump Offset Recalculation ==============

def recalculate_jumps(instructions: List[Instruction], 
                      old_to_new_pc: Dict[int, int]) -> None:
    """
    Recalculate jump offsets after instruction modification.
    
    This function updates sBx fields for all jump instructions
    (JMP, FORLOOP, FORPREP, TFORLOOP) based on PC remapping.
    
    Args:
        instructions: The modified instruction list (will be updated in-place)
        old_to_new_pc: Mapping from old PC values to new PC values
        
    Raises:
        ValueError: If a jump target was removed
    """
    from .opcodes import Opcode
    
    # Build reverse mapping
    new_to_old_pc = {v: k for k, v in old_to_new_pc.items()}
    
    jump_opcodes = {Opcode.JMP, Opcode.FORLOOP, Opcode.FORPREP, Opcode.TFORLOOP}
    
    for new_pc, instr in enumerate(instructions):
        if instr.opcode in jump_opcodes:
            # Find the original PC for this instruction
            old_current_pc = new_to_old_pc.get(new_pc)
            if old_current_pc is None:
                # This is a newly inserted instruction
                continue
            
            # Calculate original target PC
            old_target_pc = old_current_pc + 1 + instr.sbx
            
            # Find new target PC
            new_target_pc = old_to_new_pc.get(old_target_pc)
            if new_target_pc is None:
                raise ValueError(
                    f"Jump target at PC {old_target_pc} was removed "
                    f"(jump from PC {old_current_pc}, now at {new_pc})"
                )
            
            # Calculate and update new sBx
            new_sbx = new_target_pc - (new_pc + 1)
            instr.sbx = new_sbx
            
            # Also update bx for consistency
            instr.bx = new_sbx + MAXARG_sBx
            
            # Clear raw since we modified the instruction
            instr.raw = None


def update_instruction_raw(instr: Instruction) -> None:
    """
    Update the raw field of an instruction after modification.
    
    Call this after modifying instruction fields to ensure
    the raw value is consistent.
    
    Args:
        instr: The instruction to update
    """
    instr.raw = LuaBytecodeSerializer.encode_instruction(instr)


# ============== Round-Trip Testing Utilities ==============

def verify_round_trip(original_data: bytes) -> tuple:
    """
    Verify that parse -> serialize produces identical or equivalent bytes.
    
    Args:
        original_data: Original bytecode bytes
        
    Returns:
        tuple: (success: bool, message: str)
        
    Note: Some files may have trailing data (e.g., watermarks, comments)
    that are not part of the Lua bytecode. This function considers the
    round-trip successful if the serialized output matches the parsed
    portion of the original file.
    """
    from .parser import parse_bytes
    
    # Parse
    chunk = parse_bytes(original_data)
    
    # Serialize
    serialized = serialize_chunk(chunk)
    
    # Check if the serialized data matches the beginning of original
    if original_data == serialized:
        return True, f"Exact match: {len(serialized)} bytes"
    
    if original_data[:len(serialized)] == serialized:
        extra = len(original_data) - len(serialized)
        return True, f"Match with {extra} bytes trailing data ignored"
    
    # Find first difference
    min_len = min(len(original_data), len(serialized))
    for i in range(min_len):
        if original_data[i] != serialized[i]:
            return False, (
                f"Mismatch at byte {i}: "
                f"original=0x{original_data[i]:02x}, serialized=0x{serialized[i]:02x}"
            )
    
    return False, f"Length mismatch: original={len(original_data)}, serialized={len(serialized)}"


def verify_round_trip_file(filepath: str) -> tuple:
    """
    Verify round-trip for a file.
    
    Args:
        filepath: Path to the Lua bytecode file
        
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        with open(filepath, 'rb') as f:
            original = f.read()
        
        return verify_round_trip(original)
    
    except Exception as e:
        return False, f"Error: {e}"


def compare_prototypes(proto1: Prototype, proto2: Prototype, path: str = "main") -> List[str]:
    """
    Compare two prototypes and return list of differences.
    
    Args:
        proto1: First prototype
        proto2: Second prototype
        path: Path string for error messages
        
    Returns:
        List of difference descriptions (empty if identical)
    """
    diffs = []
    
    # Compare basic fields
    if proto1.source != proto2.source:
        diffs.append(f"{path}: source mismatch: '{proto1.source}' vs '{proto2.source}'")
    if proto1.line_defined != proto2.line_defined:
        diffs.append(f"{path}: line_defined mismatch: {proto1.line_defined} vs {proto2.line_defined}")
    if proto1.last_line_defined != proto2.last_line_defined:
        diffs.append(f"{path}: last_line_defined mismatch")
    if proto1.num_params != proto2.num_params:
        diffs.append(f"{path}: num_params mismatch: {proto1.num_params} vs {proto2.num_params}")
    if proto1.is_vararg != proto2.is_vararg:
        diffs.append(f"{path}: is_vararg mismatch")
    if proto1.max_stack_size != proto2.max_stack_size:
        diffs.append(f"{path}: max_stack_size mismatch")
    
    # Compare code
    if len(proto1.code) != len(proto2.code):
        diffs.append(f"{path}: code length mismatch: {len(proto1.code)} vs {len(proto2.code)}")
    else:
        for i, (c1, c2) in enumerate(zip(proto1.code, proto2.code)):
            if c1.raw != c2.raw:
                diffs.append(f"{path}: instruction {i} mismatch: 0x{c1.raw:08x} vs 0x{c2.raw:08x}")
    
    # Compare constants
    if len(proto1.constants) != len(proto2.constants):
        diffs.append(f"{path}: constants count mismatch: {len(proto1.constants)} vs {len(proto2.constants)}")
    else:
        for i, (c1, c2) in enumerate(zip(proto1.constants, proto2.constants)):
            if c1.type != c2.type or c1.value != c2.value:
                diffs.append(f"{path}: constant {i} mismatch: {c1} vs {c2}")
    
    # Compare upvalues
    if len(proto1.upvalues) != len(proto2.upvalues):
        diffs.append(f"{path}: upvalues count mismatch")
    else:
        for i, (u1, u2) in enumerate(zip(proto1.upvalues, proto2.upvalues)):
            if u1.instack != u2.instack or u1.idx != u2.idx or u1.name != u2.name:
                diffs.append(f"{path}: upvalue {i} mismatch")
    
    # Compare lineinfo
    if proto1.lineinfo != proto2.lineinfo:
        diffs.append(f"{path}: lineinfo mismatch")
    
    # Compare locvars
    if len(proto1.locvars) != len(proto2.locvars):
        diffs.append(f"{path}: locvars count mismatch")
    
    # Compare child prototypes
    if len(proto1.protos) != len(proto2.protos):
        diffs.append(f"{path}: child protos count mismatch: {len(proto1.protos)} vs {len(proto2.protos)}")
    else:
        for i, (p1, p2) in enumerate(zip(proto1.protos, proto2.protos)):
            diffs.extend(compare_prototypes(p1, p2, f"{path}/F{i}"))
    
    return diffs
