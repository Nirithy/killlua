"""
Lua 5.3 Official Bytecode Serializer

Converts LuaJ/GameGuardian format to official Lua 5.3 bytecode format.
The converted bytecode can be run with the official Lua 5.3 interpreter.

Key differences from LuaJ format:
1. Header format is different (Lua 5.3 style)
2. Opcode numbers are different in some cases
3. Some custom LuaJ opcodes need to be converted to equivalent Lua 5.3 sequences
4. Constant types are different (Lua 5.3 has separate integer type)
5. String format uses varint size instead of fixed size_t
"""

from typing import List, Optional, Dict, Tuple, Any
from enum import IntEnum
import struct
import math

from .parser import (
    LuaChunk, LuaHeader, Prototype, Instruction, LuaConstant, 
    Upvalue, LocVar, LuaConstantType
)
from .opcodes import OpMode, get_opcode_mode, MAXARG_sBx, Opcode


# ============== Lua 5.3 Official Opcodes ==============

class Lua53Opcode(IntEnum):
    """Official Lua 5.3 Opcodes"""
    MOVE = 0
    LOADK = 1
    LOADKX = 2
    LOADBOOL = 3
    LOADNIL = 4
    GETUPVAL = 5
    GETTABUP = 6
    GETTABLE = 7
    SETTABUP = 8
    SETUPVAL = 9
    SETTABLE = 10
    NEWTABLE = 11
    SELF = 12
    ADD = 13
    SUB = 14
    MUL = 15
    MOD = 16      # Note: Different position from LuaJ
    POW = 17      # Note: Different position from LuaJ
    DIV = 18      # Note: Different position from LuaJ
    IDIV = 19     # Note: Different position from LuaJ
    BAND = 20     # Note: Different position from LuaJ
    BOR = 21      # Note: Different position from LuaJ
    BXOR = 22     # Note: Different position from LuaJ
    SHL = 23      # Note: Different position from LuaJ
    SHR = 24      # Note: Different position from LuaJ
    UNM = 25      # Note: Different position from LuaJ
    BNOT = 26     # Note: Different position from LuaJ
    NOT = 27      # Note: Different position from LuaJ
    LEN = 28      # Note: Different position from LuaJ
    CONCAT = 29   # Note: Different position from LuaJ
    JMP = 30      # Note: Different position from LuaJ
    EQ = 31       # Note: Different position from LuaJ
    LT = 32       # Note: Different position from LuaJ
    LE = 33       # Note: Different position from LuaJ
    TEST = 34     # Note: Different position from LuaJ
    TESTSET = 35  # Note: Different position from LuaJ
    CALL = 36     # Note: Different position from LuaJ
    TAILCALL = 37 # Note: Different position from LuaJ
    RETURN = 38   # Note: Different position from LuaJ
    FORLOOP = 39  # Note: Different position from LuaJ
    FORPREP = 40  # Note: Different position from LuaJ
    TFORCALL = 41 # Note: Different position from LuaJ
    TFORLOOP = 42 # Note: Different position from LuaJ
    SETLIST = 43  # Note: Different position from LuaJ
    CLOSURE = 44  # Note: Different position from LuaJ
    VARARG = 45   # Note: Different position from LuaJ
    EXTRAARG = 46 # Note: Different position from LuaJ


# LuaJ opcode to Lua 5.3 opcode mapping
LUAJ_TO_LUA53_OPCODE: Dict[int, int] = {
    # Same opcodes (0-15 are mostly the same)
    Opcode.MOVE: Lua53Opcode.MOVE,
    Opcode.LOADK: Lua53Opcode.LOADK,
    Opcode.LOADKX: Lua53Opcode.LOADKX,
    Opcode.LOADBOOL: Lua53Opcode.LOADBOOL,
    Opcode.LOADNIL: Lua53Opcode.LOADNIL,
    Opcode.GETUPVAL: Lua53Opcode.GETUPVAL,
    Opcode.GETTABUP: Lua53Opcode.GETTABUP,
    Opcode.GETTABLE: Lua53Opcode.GETTABLE,
    Opcode.SETTABUP: Lua53Opcode.SETTABUP,
    Opcode.SETUPVAL: Lua53Opcode.SETUPVAL,
    Opcode.SETTABLE: Lua53Opcode.SETTABLE,
    Opcode.NEWTABLE: Lua53Opcode.NEWTABLE,
    Opcode.SELF: Lua53Opcode.SELF,
    Opcode.ADD: Lua53Opcode.ADD,
    Opcode.SUB: Lua53Opcode.SUB,
    Opcode.MUL: Lua53Opcode.MUL,
    # Remapped opcodes
    Opcode.DIV: Lua53Opcode.DIV,       # 16 -> 18
    Opcode.MOD: Lua53Opcode.MOD,       # 17 -> 16
    Opcode.POW: Lua53Opcode.POW,       # 18 -> 17
    Opcode.UNM: Lua53Opcode.UNM,       # 19 -> 25
    Opcode.NOT: Lua53Opcode.NOT,       # 20 -> 27
    Opcode.LEN: Lua53Opcode.LEN,       # 21 -> 28
    Opcode.CONCAT: Lua53Opcode.CONCAT, # 22 -> 29
    Opcode.JMP: Lua53Opcode.JMP,       # 23 -> 30
    Opcode.EQ: Lua53Opcode.EQ,         # 24 -> 31
    Opcode.LT: Lua53Opcode.LT,         # 25 -> 32
    Opcode.LE: Lua53Opcode.LE,         # 26 -> 33
    Opcode.TEST: Lua53Opcode.TEST,     # 27 -> 34
    Opcode.TESTSET: Lua53Opcode.TESTSET, # 28 -> 35
    Opcode.CALL: Lua53Opcode.CALL,     # 29 -> 36
    Opcode.TAILCALL: Lua53Opcode.TAILCALL, # 30 -> 37
    Opcode.RETURN: Lua53Opcode.RETURN, # 31 -> 38
    Opcode.FORLOOP: Lua53Opcode.FORLOOP, # 32 -> 39
    Opcode.FORPREP: Lua53Opcode.FORPREP, # 33 -> 40
    Opcode.TFORCALL: Lua53Opcode.TFORCALL, # 34 -> 41
    Opcode.TFORLOOP: Lua53Opcode.TFORLOOP, # 35 -> 42
    Opcode.SETLIST: Lua53Opcode.SETLIST, # 36 -> 43
    Opcode.CLOSURE: Lua53Opcode.CLOSURE, # 37 -> 44
    Opcode.VARARG: Lua53Opcode.VARARG, # 38 -> 45
    Opcode.EXTRAARG: Lua53Opcode.EXTRAARG, # 39 -> 46
    # Lua 5.3 specific opcodes
    Opcode.IDIV: Lua53Opcode.IDIV,     # 40 -> 19
    Opcode.BNOT: Lua53Opcode.BNOT,     # 41 -> 26
    Opcode.BAND: Lua53Opcode.BAND,     # 42 -> 20
    Opcode.BOR: Lua53Opcode.BOR,       # 43 -> 21
    Opcode.BXOR: Lua53Opcode.BXOR,     # 44 -> 22
    Opcode.SHL: Lua53Opcode.SHL,       # 45 -> 23
    Opcode.SHR: Lua53Opcode.SHR,       # 46 -> 24
}


# Lua 5.3 instruction modes
LUA53_OPCODE_MODES: Dict[int, OpMode] = {
    Lua53Opcode.MOVE: OpMode.iABC,
    Lua53Opcode.LOADK: OpMode.iABx,
    Lua53Opcode.LOADKX: OpMode.iABx,
    Lua53Opcode.LOADBOOL: OpMode.iABC,
    Lua53Opcode.LOADNIL: OpMode.iABC,
    Lua53Opcode.GETUPVAL: OpMode.iABC,
    Lua53Opcode.GETTABUP: OpMode.iABC,
    Lua53Opcode.GETTABLE: OpMode.iABC,
    Lua53Opcode.SETTABUP: OpMode.iABC,
    Lua53Opcode.SETUPVAL: OpMode.iABC,
    Lua53Opcode.SETTABLE: OpMode.iABC,
    Lua53Opcode.NEWTABLE: OpMode.iABC,
    Lua53Opcode.SELF: OpMode.iABC,
    Lua53Opcode.ADD: OpMode.iABC,
    Lua53Opcode.SUB: OpMode.iABC,
    Lua53Opcode.MUL: OpMode.iABC,
    Lua53Opcode.MOD: OpMode.iABC,
    Lua53Opcode.POW: OpMode.iABC,
    Lua53Opcode.DIV: OpMode.iABC,
    Lua53Opcode.IDIV: OpMode.iABC,
    Lua53Opcode.BAND: OpMode.iABC,
    Lua53Opcode.BOR: OpMode.iABC,
    Lua53Opcode.BXOR: OpMode.iABC,
    Lua53Opcode.SHL: OpMode.iABC,
    Lua53Opcode.SHR: OpMode.iABC,
    Lua53Opcode.UNM: OpMode.iABC,
    Lua53Opcode.BNOT: OpMode.iABC,
    Lua53Opcode.NOT: OpMode.iABC,
    Lua53Opcode.LEN: OpMode.iABC,
    Lua53Opcode.CONCAT: OpMode.iABC,
    Lua53Opcode.JMP: OpMode.iAsBx,
    Lua53Opcode.EQ: OpMode.iABC,
    Lua53Opcode.LT: OpMode.iABC,
    Lua53Opcode.LE: OpMode.iABC,
    Lua53Opcode.TEST: OpMode.iABC,
    Lua53Opcode.TESTSET: OpMode.iABC,
    Lua53Opcode.CALL: OpMode.iABC,
    Lua53Opcode.TAILCALL: OpMode.iABC,
    Lua53Opcode.RETURN: OpMode.iABC,
    Lua53Opcode.FORLOOP: OpMode.iAsBx,
    Lua53Opcode.FORPREP: OpMode.iAsBx,
    Lua53Opcode.TFORCALL: OpMode.iABC,
    Lua53Opcode.TFORLOOP: OpMode.iAsBx,
    Lua53Opcode.SETLIST: OpMode.iABC,
    Lua53Opcode.CLOSURE: OpMode.iABx,
    Lua53Opcode.VARARG: OpMode.iABC,
    Lua53Opcode.EXTRAARG: OpMode.iAx,
}


# ============== Lua 5.3 Constant Types ==============

class Lua53ConstantType(IntEnum):
    """Lua 5.3 constant types"""
    NIL = 0
    BOOLEAN = 1
    NUMBER = 3       # lua_Number (float)
    INTEGER = 0x13   # lua_Integer (NUMFLT | (1 << 4))
    SHORTSTR = 4     # short string
    LONGSTR = 0x14   # long string (4 | (1 << 4))


# ============== Lua 5.3 Serializer ==============

class Lua53Serializer:
    """
    Serializes LuaChunk objects to official Lua 5.3 bytecode format.
    
    Lua 5.3 header format:
    - Signature: 4 bytes (0x1B 'L' 'u' 'a')
    - Version: 1 byte (0x53)
    - Format: 1 byte (0)
    - LUAC_DATA: 6 bytes (0x19 0x93 0x0D 0x0A 0x1A 0x0A)
    - sizeof(int): 1 byte (4)
    - sizeof(size_t): 1 byte (8)
    - sizeof(Instruction): 1 byte (4)
    - sizeof(lua_Integer): 1 byte (8)
    - sizeof(lua_Number): 1 byte (8)
    - LUAC_INT: 8 bytes (0x5678 as lua_Integer)
    - LUAC_NUM: 8 bytes (370.5 as lua_Number)
    """
    
    # Lua 5.3 header constants
    LUA_SIGNATURE = b'\x1bLua'
    LUA_VERSION = 0x53
    LUAC_FORMAT = 0x00
    LUAC_DATA = b'\x19\x93\r\n\x1a\n'
    LUAC_INT = 0x5678
    LUAC_NUM = 370.5
    
    def __init__(self, chunk: LuaChunk):
        """
        Initialize the serializer with a LuaChunk.
        
        Args:
            chunk: The LuaChunk to serialize (in LuaJ format)
        """
        self.chunk = chunk
        self.buffer = bytearray()
        
        # Lua 5.3 default sizes
        self.size_int = 4
        self.size_size_t = 8
        self.size_instruction = 4
        self.size_lua_integer = 8
        self.size_lua_number = 8
        
        # Track unsupported opcodes for warnings
        self.warnings: List[str] = []
    
    # ============== Basic Write Methods ==============
    
    def write_byte(self, value: int) -> None:
        """Write a single byte"""
        self.buffer.append(value & 0xFF)
    
    def write_bytes(self, data: bytes) -> None:
        """Write raw bytes"""
        self.buffer.extend(data)
    
    def write_int(self, value: int) -> None:
        """Write a 4-byte signed integer (little endian)"""
        self.buffer.extend(struct.pack('<i', value))
    
    def write_uint(self, value: int) -> None:
        """Write a 4-byte unsigned integer (little endian)"""
        self.buffer.extend(struct.pack('<I', value))
    
    def write_size_t(self, value: int) -> None:
        """Write a size_t (8 bytes for Lua 5.3)"""
        self.buffer.extend(struct.pack('<Q', value))
    
    def write_lua_integer(self, value: int) -> None:
        """Write a lua_Integer (8 bytes, signed)"""
        self.buffer.extend(struct.pack('<q', value))
    
    def write_lua_number(self, value: float) -> None:
        """Write a lua_Number (8 bytes double)"""
        self.buffer.extend(struct.pack('<d', value))
    
    def write_instruction(self, value: int) -> None:
        """Write a 32-bit instruction"""
        self.buffer.extend(struct.pack('<I', value))
    
    def write_string(self, value: Optional[str]) -> None:
        """
        Write a Lua 5.3 string.
        
        Lua 5.3 string format (from lundump.c):
        - 0x00: NULL string
        - 0x01-0xFD: short string, byte = size (including null terminator in logic)
        - 0xFF: long string, followed by size_t
        
        Note: The size written is len+1 where len is string length.
        For short strings: if len+1 < 0xFF, write single byte
        For long strings: write 0xFF then size_t of actual length
        """
        if value is None:
            self.write_byte(0)  # NULL string
            return
        
        # Encode string
        try:
            encoded = value.encode('utf-8')
        except UnicodeEncodeError:
            encoded = value.encode('latin-1')
        
        size = len(encoded) + 1  # +1 follows Lua convention
        
        if size < 0xFF:
            self.write_byte(size)
        else:
            self.write_byte(0xFF)
            self.write_size_t(size)
        
        self.buffer.extend(encoded)
    
    # ============== Opcode Conversion ==============
    
    def convert_opcode(self, luaj_opcode: int) -> Tuple[int, bool]:
        """
        Convert LuaJ opcode to Lua 5.3 opcode.
        
        Returns:
            Tuple of (lua53_opcode, is_supported)
        """
        if luaj_opcode in LUAJ_TO_LUA53_OPCODE:
            return LUAJ_TO_LUA53_OPCODE[luaj_opcode], True
        
        # Custom LuaJ opcodes that need special handling
        # GETFIELDU (47), GETFIELDT (48), CLASS (49), OR (59), AND (60), 
        # NEQ (61), GE (62), GT (63)
        return luaj_opcode, False
    
    def convert_instruction(self, instr: Instruction) -> List[int]:
        """
        Convert a LuaJ instruction to Lua 5.3 instruction(s).
        
        Some LuaJ custom opcodes need to be converted to sequences of
        standard Lua 5.3 instructions.
        
        Returns:
            List of encoded 32-bit instructions
        """
        lua53_opcode, supported = self.convert_opcode(instr.opcode)
        
        if supported:
            # Direct conversion - just remap the opcode
            mode = LUA53_OPCODE_MODES.get(lua53_opcode, OpMode.iABC)
            return [self._encode_instruction(lua53_opcode, instr, mode)]
        
        # Handle unsupported/custom opcodes
        opcode_name = Opcode(instr.opcode).name if instr.opcode in [e.value for e in Opcode] else f"UNKNOWN_{instr.opcode}"
        
        # Try to convert custom opcodes to equivalent sequences
        if instr.opcode == Opcode.NEQ:
            # NEQ A B C -> EQ A B C with inverted A
            # NEQ: if ((RK(B) ~= RK(C)) ~= A) then pc++
            # EQ:  if ((RK(B) == RK(C)) ~= A) then pc++
            # NEQ with A=0 is equivalent to EQ with A=1
            inverted_a = 1 if instr.a == 0 else 0
            return [self._encode_iABC(Lua53Opcode.EQ, inverted_a, instr.b, instr.c)]
        
        elif instr.opcode == Opcode.GT:
            # GT A B C -> LT A C B (swap operands)
            # GT: if ((RK(B) > RK(C)) ~= A) then pc++
            # LT: if ((RK(B) < RK(C)) ~= A) then pc++
            return [self._encode_iABC(Lua53Opcode.LT, instr.a, instr.c, instr.b)]
        
        elif instr.opcode == Opcode.GE:
            # GE A B C -> LE A C B (swap operands)
            # GE: if ((RK(B) >= RK(C)) ~= A) then pc++
            # LE: if ((RK(B) <= RK(C)) ~= A) then pc++
            return [self._encode_iABC(Lua53Opcode.LE, instr.a, instr.c, instr.b)]
        
        elif instr.opcode == Opcode.GETFIELDU:
            # GETFIELDU A B C -> GETTABUP A B C
            # They are functionally equivalent
            return [self._encode_iABC(Lua53Opcode.GETTABUP, instr.a, instr.b, instr.c)]
        
        elif instr.opcode == Opcode.GETFIELDT:
            # GETFIELDT A B C -> GETTABLE A B C
            return [self._encode_iABC(Lua53Opcode.GETTABLE, instr.a, instr.b, instr.c)]
        
        elif instr.opcode == Opcode.OR:
            # Custom OR opcode - this is complex, need runtime support
            # For now, warn and try to preserve semantics
            self.warnings.append(f"Custom OR opcode at instruction - may not work correctly")
            # Try TESTSET sequence (approximate)
            return [self._encode_iABC(Lua53Opcode.TESTSET, instr.a, instr.b, 1)]
        
        elif instr.opcode == Opcode.AND:
            # Custom AND opcode - similar to OR
            self.warnings.append(f"Custom AND opcode at instruction - may not work correctly")
            return [self._encode_iABC(Lua53Opcode.TESTSET, instr.a, instr.b, 0)]
        
        elif instr.opcode == Opcode.CLASS:
            # Custom CLASS opcode - GameGuardian specific
            # Keep original raw instruction as it's likely dead code
            self.warnings.append(f"Custom CLASS opcode - keeping raw instruction (likely dead code)")
            return [instr.raw]
        
        else:
            # Unknown opcode (50-58, etc.) - likely obfuscator junk/dead code
            # Keep original raw instruction as-is since it will never be executed
            self.warnings.append(f"Unknown opcode {opcode_name} ({instr.opcode}) - keeping raw instruction (junk/dead code)")
            return [instr.raw]
    
    def _encode_instruction(self, opcode: int, instr: Instruction, mode: OpMode) -> int:
        """Encode instruction with given opcode using original operands"""
        if mode == OpMode.iABC:
            return self._encode_iABC(opcode, instr.a, instr.b, instr.c)
        elif mode == OpMode.iABx:
            return self._encode_iABx(opcode, instr.a, instr.bx)
        elif mode == OpMode.iAsBx:
            return self._encode_iAsBx(opcode, instr.a, instr.sbx)
        elif mode == OpMode.iAx:
            return self._encode_iAx(opcode, instr.ax)
        return 0
    
    def _encode_iABC(self, opcode: int, a: int, b: int, c: int) -> int:
        """Encode iABC format instruction"""
        return ((opcode & 0x3F) |
                ((a & 0xFF) << 6) |
                ((c & 0x1FF) << 14) |
                ((b & 0x1FF) << 23))
    
    def _encode_iABx(self, opcode: int, a: int, bx: int) -> int:
        """Encode iABx format instruction"""
        return ((opcode & 0x3F) |
                ((a & 0xFF) << 6) |
                ((bx & 0x3FFFF) << 14))
    
    def _encode_iAsBx(self, opcode: int, a: int, sbx: int) -> int:
        """Encode iAsBx format instruction"""
        sbx_encoded = sbx + MAXARG_sBx
        return ((opcode & 0x3F) |
                ((a & 0xFF) << 6) |
                ((sbx_encoded & 0x3FFFF) << 14))
    
    def _encode_iAx(self, opcode: int, ax: int) -> int:
        """Encode iAx format instruction"""
        return ((opcode & 0x3F) |
                ((ax & 0x3FFFFFF) << 6))
    
    # ============== Constant Conversion ==============
    
    def convert_constant(self, const: LuaConstant) -> Tuple[int, Any]:
        """
        Convert LuaJ constant to Lua 5.3 format.
        
        Returns:
            Tuple of (lua53_type, value)
        """
        if const.type == LuaConstantType.NIL:
            return Lua53ConstantType.NIL, None
        
        elif const.type == LuaConstantType.BOOLEAN:
            return Lua53ConstantType.BOOLEAN, const.value
        
        elif const.type == LuaConstantType.NUMBER:
            # Check if it's an integer that fits in 64-bit signed range
            if isinstance(const.value, float) and const.value.is_integer():
                int_val = int(const.value)
                if -9223372036854775808 <= int_val <= 9223372036854775807:
                    return Lua53ConstantType.INTEGER, int_val
            return Lua53ConstantType.NUMBER, const.value
        
        elif const.type == LuaConstantType.INT:
            # Check if value fits in 64-bit signed integer range
            val = const.value
            if -9223372036854775808 <= val <= 9223372036854775807:
                return Lua53ConstantType.INTEGER, val
            else:
                # Value out of range, store as float
                return Lua53ConstantType.NUMBER, float(val)
        
        elif const.type == LuaConstantType.STRING:
            # Use short string for shorter strings
            if const.value and len(const.value) < 40:
                return Lua53ConstantType.SHORTSTR, const.value
            return Lua53ConstantType.LONGSTR, const.value
        
        elif const.type == LuaConstantType.BIGNUMBER:
            # BigNumber stored as string - try to convert to number
            try:
                val = int(const.value)
                # Check if value fits in 64-bit signed integer range
                if -9223372036854775808 <= val <= 9223372036854775807:
                    return Lua53ConstantType.INTEGER, val
                else:
                    # Value out of range for integer, try as float
                    return Lua53ConstantType.NUMBER, float(val)
            except (ValueError, TypeError):
                try:
                    val = float(const.value)
                    return Lua53ConstantType.NUMBER, val
                except (ValueError, TypeError):
                    # Keep as string if conversion fails
                    return Lua53ConstantType.SHORTSTR, str(const.value)
        
        else:
            raise ValueError(f"Unknown constant type: {const.type}")
    
    # ============== High-Level Serialization ==============
    
    def serialize_header(self) -> None:
        """Serialize Lua 5.3 header"""
        # Signature
        self.write_bytes(self.LUA_SIGNATURE)
        
        # Version (0x53 for Lua 5.3)
        self.write_byte(self.LUA_VERSION)
        
        # Format (official format = 0)
        self.write_byte(self.LUAC_FORMAT)
        
        # LUAC_DATA (verification data)
        self.write_bytes(self.LUAC_DATA)
        
        # Size configuration
        self.write_byte(self.size_int)           # sizeof(int) = 4
        self.write_byte(self.size_size_t)        # sizeof(size_t) = 8
        self.write_byte(self.size_instruction)   # sizeof(Instruction) = 4
        self.write_byte(self.size_lua_integer)   # sizeof(lua_Integer) = 8
        self.write_byte(self.size_lua_number)    # sizeof(lua_Number) = 8
        
        # LUAC_INT (integer test value)
        self.write_lua_integer(self.LUAC_INT)
        
        # LUAC_NUM (float test value)
        self.write_lua_number(self.LUAC_NUM)
    
    def serialize_constants(self, constants: List[LuaConstant]) -> None:
        """Serialize constants array in Lua 5.3 format"""
        self.write_int(len(constants))
        
        for const in constants:
            lua53_type, value = self.convert_constant(const)
            
            # Write type byte
            self.write_byte(lua53_type)
            
            if lua53_type == Lua53ConstantType.NIL:
                pass  # No data
            
            elif lua53_type == Lua53ConstantType.BOOLEAN:
                self.write_byte(1 if value else 0)
            
            elif lua53_type == Lua53ConstantType.NUMBER:
                self.write_lua_number(value)
            
            elif lua53_type == Lua53ConstantType.INTEGER:
                self.write_lua_integer(value)
            
            elif lua53_type in (Lua53ConstantType.SHORTSTR, Lua53ConstantType.LONGSTR):
                self.write_string(value)
    
    def serialize_upvalues(self, upvalues: List[Upvalue]) -> None:
        """Serialize upvalue descriptors"""
        self.write_int(len(upvalues))
        
        for upval in upvalues:
            self.write_byte(1 if upval.instack else 0)
            self.write_byte(upval.idx)
    
    def serialize_code(self, code: List[Instruction]) -> None:
        """Serialize code (instructions) with opcode conversion"""
        # First, convert all instructions and track expansion
        converted_code: List[int] = []
        
        for instr in code:
            converted = self.convert_instruction(instr)
            converted_code.extend(converted)
        
        # Write code
        self.write_int(len(converted_code))
        for instr_raw in converted_code:
            self.write_instruction(instr_raw)
    
    def serialize_protos(self, protos: List['Prototype'], parent_source: Optional[str] = None) -> None:
        """Serialize child prototypes"""
        self.write_int(len(protos))
        for proto in protos:
            self.serialize_prototype(proto, is_main=False, parent_source=parent_source)
    
    def serialize_debug_info(self, proto: Prototype) -> None:
        """
        Serialize debug information in Lua 5.3 format.
        
        Lua 5.3 debug format (from lundump.c LoadDebug):
        - lineinfo: n + array of ints
        - locvars: n + array of (string, int, int)
        - upvalue names: n + array of strings
        
        Note: abslineinfo is Lua 5.4 only, not present in 5.3!
        """
        # Line info (n + array of ints)
        self.write_int(len(proto.lineinfo))
        for line in proto.lineinfo:
            self.write_int(line)
        
        # Local variables (NO abslineinfo in 5.3!)
        self.write_int(len(proto.locvars))
        for locvar in proto.locvars:
            self.write_string(locvar.varname)
            self.write_int(locvar.startpc)
            self.write_int(locvar.endpc)
        
        # Upvalue names
        named_count = 0
        for upval in proto.upvalues:
            if upval.name is not None:
                named_count += 1
            else:
                break
        
        self.write_int(named_count)
        for i in range(named_count):
            self.write_string(proto.upvalues[i].name)
    
    def serialize_prototype(self, proto: Prototype, is_main: bool = False, 
                            parent_source: Optional[str] = None) -> None:
        """
        Serialize a function prototype in Lua 5.3 format.
        
        Lua 5.3 prototype format (from lundump.c LoadFunction):
        1. source name (for main function, or NULL/inherited for children)
        2. linedefined, lastlinedefined
        3. numparams, is_vararg, maxstacksize
        4. code
        5. constants
        6. upvalues
        7. protos
        8. debug (lineinfo, abslineinfo, locvars, upvalnames)
        """
        # Source name
        if is_main:
            source = proto.source or "@converted.lua"
            self.write_string(source)
        else:
            # Child functions: write source if different from parent, else NULL
            if proto.source and proto.source != parent_source:
                self.write_string(proto.source)
            else:
                self.write_byte(0)  # NULL - inherit from parent
        
        # Determine source for children
        current_source = proto.source if proto.source else parent_source
        
        # Function metadata
        self.write_int(proto.line_defined)
        self.write_int(proto.last_line_defined)
        self.write_byte(proto.num_params)
        self.write_byte(proto.is_vararg)
        self.write_byte(proto.max_stack_size)
        
        # Code
        self.serialize_code(proto.code)
        
        # Constants
        self.serialize_constants(proto.constants)
        
        # Upvalues
        self.serialize_upvalues(proto.upvalues)
        
        # Child prototypes
        self.serialize_protos(proto.protos, parent_source=current_source)
        
        # Debug info
        self.serialize_debug_info(proto)
    
    def serialize(self) -> bytes:
        """
        Serialize the complete LuaChunk to Lua 5.3 bytecode.
        
        Returns:
            bytes: The serialized Lua 5.3 bytecode
        """
        self.buffer.clear()
        self.warnings.clear()
        
        # Serialize header
        self.serialize_header()
        
        # Number of upvalues for main function (Lua 5.3 specific)
        self.write_byte(len(self.chunk.main.upvalues))
        
        # Serialize main prototype
        self.serialize_prototype(self.chunk.main, is_main=True)
        
        return bytes(self.buffer)
    
    def get_warnings(self) -> List[str]:
        """Get list of warnings generated during conversion"""
        return self.warnings.copy()


# ============== Public API ==============

def convert_to_lua53(chunk: LuaChunk) -> Tuple[bytes, List[str]]:
    """
    Convert a LuaJ/GameGuardian chunk to Lua 5.3 bytecode.
    
    Args:
        chunk: The LuaChunk to convert
        
    Returns:
        Tuple of (bytecode, warnings)
    """
    serializer = Lua53Serializer(chunk)
    bytecode = serializer.serialize()
    return bytecode, serializer.get_warnings()


def convert_file_to_lua53(input_path: str, output_path: str) -> List[str]:
    """
    Convert a LuaJ/GameGuardian .luac file to Lua 5.3 format.
    
    Args:
        input_path: Path to input .luac file (LuaJ format)
        output_path: Path to output .luac file (Lua 5.3 format)
        
    Returns:
        List of warnings generated during conversion
    """
    from .parser import parse_file
    
    # Parse input file
    chunk = parse_file(input_path)
    
    # Convert to Lua 5.3
    bytecode, warnings = convert_to_lua53(chunk)
    
    # Write output
    with open(output_path, 'wb') as f:
        f.write(bytecode)
    
    return warnings


def main():
    """Command line interface for conversion"""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python -m src.lua53_serializer <input.luac> <output.luac>")
        print("\nConverts LuaJ/GameGuardian bytecode to official Lua 5.3 format.")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    try:
        warnings = convert_file_to_lua53(input_path, output_path)
        
        print(f"Successfully converted: {input_path} -> {output_path}")
        
        if warnings:
            print("\nWarnings:")
            for w in warnings:
                print(f"  - {w}")
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
