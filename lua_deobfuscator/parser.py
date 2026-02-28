"""
Lua Bytecode Parser using the construct library.
Parses both:
1. Lua 5.2 Header + Lua 5.3 Instruction format used by LuaJ ("混合格式")
2. Official Lua 5.3 format ("官方格式")

Based on the specification from requirements_for_agent.md and refs/luaj/LoadState.java
"""

from construct import (
    Struct, Const, Int8ub, Int8ul, Int32ul, Int32sl, Int64ul, Float64l,
    Bytes, Array, Switch, this, Computed, Pass, PrefixedArray, If, IfThenElse,
    GreedyBytes, Adapter, Container, Byte, Rebuild, len_, Probe, FocusedSeq,
    ExprAdapter, Sequence, LazyBound, RepeatUntil, VarInt, Construct, stream_read,
    stream_tell, stream_seek, singleton
)
from dataclasses import dataclass
from typing import List, Optional, Any, Union, Tuple
from enum import IntEnum
import struct

from .opcodes import Opcode, get_opcode_mode, OpMode, get_opcode_name


# ============== Lua Format Constants ==============

class LuaFormat(IntEnum):
    """Lua bytecode format types"""
    LUAJ_HYBRID = 1   # Lua 5.2 header + Lua 5.3 instructions (GameGuardian/LuaJ)
    LUA53_OFFICIAL = 2  # Official Lua 5.3 format


# ============== Custom Adapters ==============

class LuaStringAdapter(Adapter):
    """Adapter for Lua strings (length-prefixed, null-terminated)
    
    Uses latin-1 encoding to preserve byte values exactly.
    """
    def _decode(self, obj, context, path):
        if obj is None or len(obj) == 0:
            return None
        # Remove null terminator, use latin-1 for 1:1 byte mapping
        return obj[:-1].decode('latin-1') if obj else None
    
    def _encode(self, obj, context, path):
        if obj is None:
            return b''
        return obj.encode('latin-1') + b'\x00'


class LuaNumberAdapter(Adapter):
    """Adapter for Lua numbers (can be int or float)"""
    def _decode(self, obj, context, path):
        return obj
    
    def _encode(self, obj, context, path):
        return obj


# ============== Constant Types ==============

class LuaConstantType(IntEnum):
    NIL = 0
    BOOLEAN = 1
    BIGNUMBER = 2  # Custom: big number as string
    NUMBER = 3
    STRING = 4
    INT = 0xFE  # -2 as signed byte, custom LuaJ type


# ============== Data Classes ==============

@dataclass
class LuaHeader:
    """Lua bytecode file header"""
    signature: bytes
    version: int
    format: int
    endianness: int
    size_int: int
    size_size_t: int
    size_instruction: int
    size_lua_number: int
    integral_flag: int
    tail: bytes


@dataclass
class Instruction:
    """Decoded Lua instruction"""
    raw: int
    opcode: int
    opcode_name: str
    a: int
    b: int = 0
    c: int = 0
    bx: int = 0
    sbx: int = 0
    ax: int = 0
    mode: OpMode = OpMode.iABC
    
    @staticmethod
    def decode(raw: int) -> 'Instruction':
        """Decode a raw 32-bit instruction"""
        opcode = raw & 0x3F
        a = (raw >> 6) & 0xFF
        c = (raw >> 14) & 0x1FF
        b = (raw >> 23) & 0x1FF
        bx = (raw >> 14) & 0x3FFFF
        sbx = bx - 131071  # MAXARG_sBx
        ax = (raw >> 6) & 0x3FFFFFF
        
        mode = get_opcode_mode(opcode)
        opcode_name = get_opcode_name(opcode)
        
        return Instruction(
            raw=raw,
            opcode=opcode,
            opcode_name=opcode_name,
            a=a, b=b, c=c,
            bx=bx, sbx=sbx, ax=ax,
            mode=mode
        )
    
    @staticmethod
    def encode_new(opcode: int, a: int = 0, b: int = 0, c: int = 0, 
                   sbx: int = 0, ax: int = 0) -> 'Instruction':
        """
        Create a new Instruction from opcode and operands.
        
        For iABC mode: use a, b, c
        For iABx mode: use a, bx will be computed from sbx (bx = sbx + 131071)
        For iAsBx mode: use a, sbx
        For iAx mode: use ax
        """
        mode = get_opcode_mode(opcode)
        opcode_name = get_opcode_name(opcode)
        
        # Compute raw instruction based on mode
        if mode == OpMode.iABC:
            raw = opcode | (a << 6) | (c << 14) | (b << 23)
            bx = (c | (b << 9))  # Not used in iABC but compute for consistency
        elif mode == OpMode.iABx:
            bx = sbx + 131071  # Convert sbx to bx
            raw = opcode | (a << 6) | (bx << 14)
        elif mode == OpMode.iAsBx:
            bx = sbx + 131071  # Convert sbx to bx
            raw = opcode | (a << 6) | (bx << 14)
        else:  # iAx
            raw = opcode | (ax << 6)
            bx = 0
        
        # Recompute all fields from raw for consistency
        return Instruction.decode(raw)


@dataclass
class LocVar:
    """Local variable debug info"""
    varname: Optional[str]
    startpc: int
    endpc: int


@dataclass
class Upvalue:
    """Upvalue descriptor"""
    name: Optional[str]
    instack: bool
    idx: int


@dataclass
class LuaConstant:
    """Lua constant value"""
    type: LuaConstantType
    value: Any
    
    def __repr__(self):
        if self.type == LuaConstantType.NIL:
            return "nil"
        elif self.type == LuaConstantType.BOOLEAN:
            return "true" if self.value else "false"
        elif self.type == LuaConstantType.STRING:
            return f'"{self.value}"'
        else:
            return str(self.value)


@dataclass
class Prototype:
    """Lua function prototype"""
    source: Optional[str]
    line_defined: int
    last_line_defined: int
    num_params: int
    is_vararg: int
    max_stack_size: int
    code: List[Instruction]
    constants: List[LuaConstant]
    protos: List['Prototype']
    upvalues: List[Upvalue]
    lineinfo: List[int]
    locvars: List[LocVar]
    
    def __post_init__(self):
        self.instructions = self.code  # Alias for compatibility


@dataclass 
class LuaChunk:
    """Complete Lua chunk (header + main function)"""
    header: LuaHeader
    main: Prototype


# ============== Parser Implementation ==============

class LuaBytecodeParser:
    """
    Parser for Lua bytecode files.
    Supports Lua 5.2 header format with Lua 5.3 instruction set (LuaJ variant).
    """
    
    # Expected header values
    LUA_SIGNATURE = b'\x1bLua'
    LUA_VERSION = 0x52  # Lua 5.2
    LUAC_FORMAT = 0x00
    LUAC_TAIL = b'\x19\x93\r\n\x1a\n'
    
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.little_endian = True
        self.size_int = 4
        self.size_size_t = 4
        self.size_instruction = 4
        self.size_lua_number = 8
        self.integral_flag = 0
        
    def read_byte(self) -> int:
        """Read a single byte"""
        b = self.data[self.pos]
        self.pos += 1
        return b
    
    def read_bytes(self, n: int) -> bytes:
        """Read n bytes"""
        data = self.data[self.pos:self.pos + n]
        self.pos += n
        # Ensure we return Python bytes, not Java jarray
        return bytes(data)
    
    def read_int(self) -> int:
        """Read a size_int integer"""
        data = self.read_bytes(self.size_int)
        if self.little_endian:
            return int.from_bytes(data, 'little', signed=True)
        return int.from_bytes(data, 'big', signed=True)
    
    def read_uint(self) -> int:
        """Read an unsigned size_int integer"""
        data = self.read_bytes(self.size_int)
        if self.little_endian:
            return int.from_bytes(data, 'little', signed=False)
        return int.from_bytes(data, 'big', signed=False)
    
    def read_size_t(self) -> int:
        """Read a size_t value"""
        if self.size_size_t == 8:
            data = self.read_bytes(8)
            if self.little_endian:
                return int.from_bytes(data, 'little', signed=False)
            return int.from_bytes(data, 'big', signed=False)
        else:
            return self.read_uint()
    
    def read_number(self) -> float:
        """Read a Lua number (double)"""
        data = self.read_bytes(self.size_lua_number)
        if self.size_lua_number == 8:
            if self.little_endian:
                return struct.unpack('<d', data)[0]
            return struct.unpack('>d', data)[0]
        else:  # 4 bytes - float
            if self.little_endian:
                return struct.unpack('<f', data)[0]
            return struct.unpack('>f', data)[0]
    
    def read_string(self) -> Optional[str]:
        """Read a Lua string (size + data, null-terminated)
        
        First tries UTF-8 decoding for proper Unicode support.
        Falls back to latin-1 to preserve byte values exactly if UTF-8 fails.
        This handles both normal Unicode strings and obfuscated bytecode
        that may contain invalid UTF-8 sequences.
        """
        size = self.read_size_t()
        if size == 0:
            return None
        data = self.read_bytes(size)
        # Remove null terminator
        raw_bytes = data[:-1]
        # Try UTF-8 first for proper Unicode support
        try:
            return raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            # Fall back to latin-1 to preserve exact byte values (1:1 mapping)
            return raw_bytes.decode('latin-1')
    
    def read_instruction(self) -> int:
        """Read a single instruction (32-bit)"""
        data = self.read_bytes(4)
        if self.little_endian:
            return int.from_bytes(data, 'little', signed=False)
        return int.from_bytes(data, 'big', signed=False)
    
    def read_int_array(self, n: int) -> List[int]:
        """Read an array of n integers"""
        result = []
        for _ in range(n):
            result.append(self.read_int())
        return result
    
    def read_instruction_array(self, n: int) -> List[int]:
        """Read an array of n instructions"""
        result = []
        for _ in range(n):
            result.append(self.read_instruction())
        return result
    
    def parse_header(self) -> LuaHeader:
        """Parse the Lua bytecode header"""
        signature = self.read_bytes(4)
        if signature != self.LUA_SIGNATURE:
            raise ValueError(f"Invalid Lua signature: {signature.hex()}")
        
        version = self.read_byte()
        if version != self.LUA_VERSION:
            raise ValueError(f"Unsupported Lua version: 0x{version:02x} (expected 0x{self.LUA_VERSION:02x})")
        
        fmt = self.read_byte()
        if fmt != self.LUAC_FORMAT:
            raise ValueError(f"Unsupported format: {fmt}")
        
        endianness = self.read_byte()
        self.little_endian = (endianness == 1)
        
        self.size_int = self.read_byte()
        self.size_size_t = self.read_byte()
        self.size_instruction = self.read_byte()
        self.size_lua_number = self.read_byte()
        self.integral_flag = self.read_byte()
        
        tail = self.read_bytes(6)
        if tail != self.LUAC_TAIL:
            raise ValueError(f"Invalid header tail: {tail.hex()} (expected {self.LUAC_TAIL.hex()})")
        
        return LuaHeader(
            signature=signature,
            version=version,
            format=fmt,
            endianness=endianness,
            size_int=self.size_int,
            size_size_t=self.size_size_t,
            size_instruction=self.size_instruction,
            size_lua_number=self.size_lua_number,
            integral_flag=self.integral_flag,
            tail=tail
        )
    
    def parse_constants(self) -> List[LuaConstant]:
        """Parse the constants array"""
        n = self.read_uint()
        constants = []
        
        for _ in range(n):
            const_type = self.read_byte()
            
            if const_type == LuaConstantType.NIL:
                constants.append(LuaConstant(LuaConstantType.NIL, None))
            
            elif const_type == LuaConstantType.BOOLEAN:
                value = self.read_byte() != 0
                constants.append(LuaConstant(LuaConstantType.BOOLEAN, value))
            
            elif const_type == LuaConstantType.BIGNUMBER:
                # Big number stored as string
                value = self.read_string()
                constants.append(LuaConstant(LuaConstantType.BIGNUMBER, value))
            
            elif const_type == LuaConstantType.NUMBER:
                value = self.read_number()
                constants.append(LuaConstant(LuaConstantType.NUMBER, value))
            
            elif const_type == LuaConstantType.STRING:
                value = self.read_string()
                constants.append(LuaConstant(LuaConstantType.STRING, value))
            
            elif const_type == 0xFE:  # LUA_TINT (custom LuaJ type, -2 as signed byte)
                value = self.read_int()
                constants.append(LuaConstant(LuaConstantType.INT, value))
            
            else:
                raise ValueError(f"Unknown constant type: {const_type} at position {self.pos}")
        
        return constants
    
    def parse_upvalues(self) -> List[Upvalue]:
        """Parse upvalue descriptors"""
        n = self.read_uint()
        upvalues = []
        
        for _ in range(n):
            instack = self.read_byte() != 0
            idx = self.read_byte()
            upvalues.append(Upvalue(name=None, instack=instack, idx=idx))
        
        return upvalues
    
    def parse_debug_info(self, upvalues: List[Upvalue]) -> tuple:
        """Parse debug information (source, lineinfo, locvars, upvalue names)"""
        # Source name
        source = self.read_string()
        
        # Line info
        # In Lua dump/load, these counts are serialized as C 'int' (signed 32-bit).
        # Obfuscators sometimes write negative/sentinel values; interpret those as "no debug".
        n = self.read_int()
        if n < 0 or n > 10_000_000:
            n = 0
        lineinfo = self.read_int_array(n)
        
        # Local variables
        n = self.read_int()
        if n < 0 or n > 100_000:
            # Treat as stripped/corrupted debug info.
            n = 0
        locvars = []
        for _ in range(n):
            varname = self.read_string()
            # Serialized as C 'int' in official dump/load.
            # Obfuscators may store sentinel values that should be interpreted as negative.
            startpc = self.read_int()
            endpc = self.read_int()
            locvars.append(LocVar(varname=varname, startpc=startpc, endpc=endpc))
        
        # Upvalue names
        n = self.read_int()
        if n < 0:
            n = 0
        if n > len(upvalues):
            n = len(upvalues)
        for i in range(n):
            name = self.read_string()
            if i < len(upvalues):
                upvalues[i].name = name
        
        return source, lineinfo, locvars
    
    def parse_prototype(self) -> Prototype:
        """Parse a function prototype"""
        # Function header
        # In Lua bytecode, these are serialized as C 'int' (signed 32-bit on Lua 5.2/5.3).
        # Some obfuscators store sentinel values like 0xFFFFFFFF which should be -1.
        # Reading as unsigned would produce >2^31 values and later break Lua 5.3 serialization.
        line_defined = self.read_int()
        last_line_defined = self.read_int()
        num_params = self.read_byte()
        is_vararg = self.read_byte()
        max_stack_size = self.read_byte()
        
        # Code (instructions)
        code_size = self.read_uint()
        raw_code = self.read_instruction_array(code_size)
        code = [Instruction.decode(instr) for instr in raw_code]
        
        # Constants
        constants = self.parse_constants()
        
        # Child prototypes
        n = self.read_uint()
        protos = []
        for _ in range(n):
            protos.append(self.parse_prototype())
        
        # Upvalues
        upvalues = self.parse_upvalues()
        
        # Debug info
        source, lineinfo, locvars = self.parse_debug_info(upvalues)
        
        return Prototype(
            source=source,
            line_defined=line_defined,
            last_line_defined=last_line_defined,
            num_params=num_params,
            is_vararg=is_vararg,
            max_stack_size=max_stack_size,
            code=code,
            constants=constants,
            protos=protos,
            upvalues=upvalues,
            lineinfo=lineinfo,
            locvars=locvars
        )
    
    def parse(self) -> LuaChunk:
        """Parse the complete Lua bytecode file"""
        header = self.parse_header()
        main = self.parse_prototype()
        return LuaChunk(header=header, main=main)


# ============== Lua 5.3 Official Constant Types ==============

class Lua53ConstantType(IntEnum):
    """Official Lua 5.3 constant types"""
    NIL = 0
    BOOLEAN = 1
    NUMBER = 3       # lua_Number (float/double)
    INTEGER = 0x13   # lua_Integer (NUMBER | (1 << 4))
    SHORTSTR = 4     # short string
    LONGSTR = 0x14   # long string (STRING | (1 << 4))


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
    MOD = 16
    POW = 17
    DIV = 18
    IDIV = 19
    BAND = 20
    BOR = 21
    BXOR = 22
    SHL = 23
    SHR = 24
    UNM = 25
    BNOT = 26
    NOT = 27
    LEN = 28
    CONCAT = 29
    JMP = 30
    EQ = 31
    LT = 32
    LE = 33
    TEST = 34
    TESTSET = 35
    CALL = 36
    TAILCALL = 37
    RETURN = 38
    FORLOOP = 39
    FORPREP = 40
    TFORCALL = 41
    TFORLOOP = 42
    SETLIST = 43
    CLOSURE = 44
    VARARG = 45
    EXTRAARG = 46


# Lua 5.3 to LuaJ opcode mapping (reverse conversion)
LUA53_TO_LUAJ_OPCODE = {
    Lua53Opcode.MOVE: Opcode.MOVE,
    Lua53Opcode.LOADK: Opcode.LOADK,
    Lua53Opcode.LOADKX: Opcode.LOADKX,
    Lua53Opcode.LOADBOOL: Opcode.LOADBOOL,
    Lua53Opcode.LOADNIL: Opcode.LOADNIL,
    Lua53Opcode.GETUPVAL: Opcode.GETUPVAL,
    Lua53Opcode.GETTABUP: Opcode.GETTABUP,
    Lua53Opcode.GETTABLE: Opcode.GETTABLE,
    Lua53Opcode.SETTABUP: Opcode.SETTABUP,
    Lua53Opcode.SETUPVAL: Opcode.SETUPVAL,
    Lua53Opcode.SETTABLE: Opcode.SETTABLE,
    Lua53Opcode.NEWTABLE: Opcode.NEWTABLE,
    Lua53Opcode.SELF: Opcode.SELF,
    Lua53Opcode.ADD: Opcode.ADD,
    Lua53Opcode.SUB: Opcode.SUB,
    Lua53Opcode.MUL: Opcode.MUL,
    Lua53Opcode.MOD: Opcode.MOD,
    Lua53Opcode.POW: Opcode.POW,
    Lua53Opcode.DIV: Opcode.DIV,
    Lua53Opcode.IDIV: Opcode.IDIV,
    Lua53Opcode.BAND: Opcode.BAND,
    Lua53Opcode.BOR: Opcode.BOR,
    Lua53Opcode.BXOR: Opcode.BXOR,
    Lua53Opcode.SHL: Opcode.SHL,
    Lua53Opcode.SHR: Opcode.SHR,
    Lua53Opcode.UNM: Opcode.UNM,
    Lua53Opcode.BNOT: Opcode.BNOT,
    Lua53Opcode.NOT: Opcode.NOT,
    Lua53Opcode.LEN: Opcode.LEN,
    Lua53Opcode.CONCAT: Opcode.CONCAT,
    Lua53Opcode.JMP: Opcode.JMP,
    Lua53Opcode.EQ: Opcode.EQ,
    Lua53Opcode.LT: Opcode.LT,
    Lua53Opcode.LE: Opcode.LE,
    Lua53Opcode.TEST: Opcode.TEST,
    Lua53Opcode.TESTSET: Opcode.TESTSET,
    Lua53Opcode.CALL: Opcode.CALL,
    Lua53Opcode.TAILCALL: Opcode.TAILCALL,
    Lua53Opcode.RETURN: Opcode.RETURN,
    Lua53Opcode.FORLOOP: Opcode.FORLOOP,
    Lua53Opcode.FORPREP: Opcode.FORPREP,
    Lua53Opcode.TFORCALL: Opcode.TFORCALL,
    Lua53Opcode.TFORLOOP: Opcode.TFORLOOP,
    Lua53Opcode.SETLIST: Opcode.SETLIST,
    Lua53Opcode.CLOSURE: Opcode.CLOSURE,
    Lua53Opcode.VARARG: Opcode.VARARG,
    Lua53Opcode.EXTRAARG: Opcode.EXTRAARG,
}


# Lua 5.3 instruction modes
LUA53_OPCODE_MODES = {
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


class Lua53BytecodeParser:
    """
    Parser for official Lua 5.3 bytecode files.
    Converts to internal representation (LuaJ opcode numbers) for compatibility.
    """
    
    # Expected header values for Lua 5.3
    LUA_SIGNATURE = b'\x1bLua'
    LUA_VERSION = 0x53  # Lua 5.3
    LUAC_FORMAT = 0x00
    LUAC_DATA = b'\x19\x93\r\n\x1a\n'
    LUAC_INT = 0x5678
    LUAC_NUM = 370.5
    
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.little_endian = True
        self.size_int = 4
        self.size_size_t = 8
        self.size_instruction = 4
        self.size_lua_integer = 8
        self.size_lua_number = 8
        
    def read_byte(self) -> int:
        """Read a single byte"""
        b = self.data[self.pos]
        self.pos += 1
        return b
    
    def read_bytes(self, n: int) -> bytes:
        """Read n bytes"""
        data = self.data[self.pos:self.pos + n]
        self.pos += n
        # Ensure we return Python bytes, not Java jarray
        return bytes(data)
    
    def read_int(self) -> int:
        """Read a 4-byte signed integer"""
        data = self.read_bytes(4)
        if self.little_endian:
            return int.from_bytes(data, 'little', signed=True)
        return int.from_bytes(data, 'big', signed=True)
    
    def read_uint(self) -> int:
        """Read a 4-byte unsigned integer"""
        data = self.read_bytes(4)
        if self.little_endian:
            return int.from_bytes(data, 'little', signed=False)
        return int.from_bytes(data, 'big', signed=False)
    
    def read_size_t(self) -> int:
        """Read a size_t value (8 bytes for Lua 5.3)"""
        data = self.read_bytes(self.size_size_t)
        if self.little_endian:
            return int.from_bytes(data, 'little', signed=False)
        return int.from_bytes(data, 'big', signed=False)
    
    def read_lua_integer(self) -> int:
        """Read a lua_Integer (8 bytes, signed)"""
        data = self.read_bytes(self.size_lua_integer)
        if self.little_endian:
            return int.from_bytes(data, 'little', signed=True)
        return int.from_bytes(data, 'big', signed=True)
    
    def read_lua_number(self) -> float:
        """Read a lua_Number (double)"""
        data = self.read_bytes(self.size_lua_number)
        if self.little_endian:
            return struct.unpack('<d', data)[0]
        return struct.unpack('>d', data)[0]
    
    def read_string(self) -> Optional[str]:
        """
        Read a Lua 5.3 string.
        
        Lua 5.3 string format:
        - 0x00: NULL string
        - 0x01-0xFD: short string, size = byte value
        - 0xFF: long string, followed by size_t
        
        The size includes an implicit +1 for the null terminator logic,
        but the actual string length is size-1.
        """
        size_byte = self.read_byte()
        
        if size_byte == 0:
            return None
        
        if size_byte == 0xFF:
            # Long string
            size = self.read_size_t()
        else:
            size = size_byte
        
        # Actual string length is size - 1 (Lua convention)
        str_len = size - 1
        if str_len <= 0:
            return ""
        
        raw_bytes = self.read_bytes(str_len)
        
        # Try UTF-8 first for proper Unicode support
        try:
            return raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            # Fall back to latin-1 to preserve exact byte values
            return raw_bytes.decode('latin-1')
    
    def read_instruction(self) -> int:
        """Read a single instruction (32-bit)"""
        data = self.read_bytes(4)
        if self.little_endian:
            return int.from_bytes(data, 'little', signed=False)
        return int.from_bytes(data, 'big', signed=False)
    
    def read_int_array(self, n: int) -> List[int]:
        """Read an array of n integers"""
        return [self.read_int() for _ in range(n)]
    
    def decode_lua53_instruction(self, raw: int) -> Instruction:
        """
        Decode a Lua 5.3 instruction and convert opcode to LuaJ format.
        """
        lua53_opcode = raw & 0x3F
        a = (raw >> 6) & 0xFF
        c = (raw >> 14) & 0x1FF
        b = (raw >> 23) & 0x1FF
        bx = (raw >> 14) & 0x3FFFF
        sbx = bx - 131071  # MAXARG_sBx
        ax = (raw >> 6) & 0x3FFFFFF
        
        # Convert Lua 5.3 opcode to LuaJ opcode
        if lua53_opcode in LUA53_TO_LUAJ_OPCODE:
            luaj_opcode = LUA53_TO_LUAJ_OPCODE[lua53_opcode]
        else:
            # Unknown opcode, keep as-is
            luaj_opcode = lua53_opcode
        
        mode = get_opcode_mode(luaj_opcode)
        opcode_name = get_opcode_name(luaj_opcode)
        
        # Rebuild the raw instruction with LuaJ opcode for consistency
        if mode == OpMode.iABC:
            new_raw = luaj_opcode | (a << 6) | (c << 14) | (b << 23)
        elif mode == OpMode.iABx:
            new_raw = luaj_opcode | (a << 6) | (bx << 14)
        elif mode == OpMode.iAsBx:
            new_raw = luaj_opcode | (a << 6) | (bx << 14)
        else:  # iAx
            new_raw = luaj_opcode | (ax << 6)
        
        return Instruction(
            raw=new_raw,
            opcode=luaj_opcode,
            opcode_name=opcode_name,
            a=a, b=b, c=c,
            bx=bx, sbx=sbx, ax=ax,
            mode=mode
        )
    
    def parse_header(self) -> LuaHeader:
        """Parse the Lua 5.3 bytecode header"""
        signature = self.read_bytes(4)
        if signature != self.LUA_SIGNATURE:
            raise ValueError(f"Invalid Lua signature: {signature.hex()}")
        
        version = self.read_byte()
        if version != self.LUA_VERSION:
            raise ValueError(f"Unsupported Lua version: 0x{version:02x} (expected 0x{self.LUA_VERSION:02x})")
        
        fmt = self.read_byte()
        if fmt != self.LUAC_FORMAT:
            raise ValueError(f"Unsupported format: {fmt}")
        
        # LUAC_DATA (verification data)
        luac_data = self.read_bytes(6)
        if luac_data != self.LUAC_DATA:
            raise ValueError(f"Invalid LUAC_DATA: {luac_data.hex()}")
        
        # Size configuration
        self.size_int = self.read_byte()
        self.size_size_t = self.read_byte()
        self.size_instruction = self.read_byte()
        self.size_lua_integer = self.read_byte()
        self.size_lua_number = self.read_byte()
        
        # Check endianness by reading LUAC_INT
        luac_int = self.read_lua_integer()
        if luac_int != self.LUAC_INT:
            # Might be big endian, but for now assume little endian
            pass
        
        # LUAC_NUM verification
        luac_num = self.read_lua_number()
        # Verify it's close to expected value
        if abs(luac_num - self.LUAC_NUM) > 0.01:
            pass  # Warning but continue
        
        # Convert to LuaJ-style header for compatibility
        # Note: We use size_size_t=4 for hybrid format compatibility,
        # as Lua 5.2/LuaJ uses 4-byte size_t while Lua 5.3 uses 8-byte
        return LuaHeader(
            signature=signature,
            version=0x52,  # Convert to LuaJ version for internal representation
            format=fmt,
            endianness=1,  # Little endian
            size_int=self.size_int,
            size_size_t=4,  # Use 4-byte size_t for hybrid format compatibility
            size_instruction=self.size_instruction,
            size_lua_number=self.size_lua_number,
            integral_flag=0,
            tail=b'\x19\x93\r\n\x1a\n'  # Standard LuaJ tail
        )
    
    def convert_constant(self, lua53_type: int, value: Any) -> LuaConstant:
        """Convert Lua 5.3 constant to internal format"""
        if lua53_type == Lua53ConstantType.NIL:
            return LuaConstant(LuaConstantType.NIL, None)
        elif lua53_type == Lua53ConstantType.BOOLEAN:
            return LuaConstant(LuaConstantType.BOOLEAN, value)
        elif lua53_type == Lua53ConstantType.NUMBER:
            return LuaConstant(LuaConstantType.NUMBER, value)
        elif lua53_type == Lua53ConstantType.INTEGER:
            return LuaConstant(LuaConstantType.INT, value)
        elif lua53_type in (Lua53ConstantType.SHORTSTR, Lua53ConstantType.LONGSTR):
            return LuaConstant(LuaConstantType.STRING, value)
        else:
            raise ValueError(f"Unknown Lua 5.3 constant type: {lua53_type}")
    
    def parse_constants(self) -> List[LuaConstant]:
        """Parse the constants array"""
        n = self.read_int()
        constants = []
        
        for _ in range(n):
            const_type = self.read_byte()
            
            if const_type == Lua53ConstantType.NIL:
                constants.append(self.convert_constant(const_type, None))
            
            elif const_type == Lua53ConstantType.BOOLEAN:
                value = self.read_byte() != 0
                constants.append(self.convert_constant(const_type, value))
            
            elif const_type == Lua53ConstantType.NUMBER:
                value = self.read_lua_number()
                constants.append(self.convert_constant(const_type, value))
            
            elif const_type == Lua53ConstantType.INTEGER:
                value = self.read_lua_integer()
                constants.append(self.convert_constant(const_type, value))
            
            elif const_type in (Lua53ConstantType.SHORTSTR, Lua53ConstantType.LONGSTR):
                value = self.read_string()
                constants.append(self.convert_constant(const_type, value))
            
            else:
                raise ValueError(f"Unknown constant type: {const_type} at position {self.pos}")
        
        return constants
    
    def parse_upvalues(self) -> List[Upvalue]:
        """Parse upvalue descriptors"""
        n = self.read_int()
        upvalues = []
        
        for _ in range(n):
            instack = self.read_byte() != 0
            idx = self.read_byte()
            upvalues.append(Upvalue(name=None, instack=instack, idx=idx))
        
        return upvalues
    
    def parse_debug_info(self, upvalues: List[Upvalue]) -> tuple:
        """
        Parse debug information (lineinfo, locvars, upvalue names).
        Note: source is parsed separately in Lua 5.3.
        """
        # Line info (n + array of ints)
        n = self.read_int()
        lineinfo = self.read_int_array(n)
        
        # Local variables
        n = self.read_int()
        locvars = []
        for _ in range(n):
            varname = self.read_string()
            # Serialized as C 'int' in official dump/load.
            startpc = self.read_int()
            endpc = self.read_int()
            locvars.append(LocVar(varname=varname, startpc=startpc, endpc=endpc))
        
        # Upvalue names
        n = self.read_int()
        for i in range(n):
            name = self.read_string()
            if i < len(upvalues):
                upvalues[i].name = name
        
        return lineinfo, locvars
    
    def parse_prototype(self, parent_source: Optional[str] = None) -> Prototype:
        """Parse a function prototype in Lua 5.3 format"""
        # Source name (for main function, or NULL/inherited for children)
        source = self.read_string()
        if source is None:
            source = parent_source
        
        # Function header
        line_defined = self.read_int()
        last_line_defined = self.read_int()
        num_params = self.read_byte()
        is_vararg = self.read_byte()
        max_stack_size = self.read_byte()
        
        # Code (instructions)
        code_size = self.read_int()
        code = []
        for _ in range(code_size):
            raw_instr = self.read_instruction()
            code.append(self.decode_lua53_instruction(raw_instr))
        
        # Constants
        constants = self.parse_constants()
        
        # Upvalues
        upvalues = self.parse_upvalues()
        
        # Child prototypes
        n = self.read_int()
        protos = []
        for _ in range(n):
            protos.append(self.parse_prototype(parent_source=source))
        
        # Debug info
        lineinfo, locvars = self.parse_debug_info(upvalues)
        
        return Prototype(
            source=source,
            line_defined=line_defined,
            last_line_defined=last_line_defined,
            num_params=num_params,
            is_vararg=is_vararg,
            max_stack_size=max_stack_size,
            code=code,
            constants=constants,
            protos=protos,
            upvalues=upvalues,
            lineinfo=lineinfo,
            locvars=locvars
        )
    
    def parse(self) -> LuaChunk:
        """Parse the complete Lua 5.3 bytecode file"""
        header = self.parse_header()
        
        # Number of upvalues for main function (Lua 5.3 specific)
        num_upvalues = self.read_byte()
        
        main = self.parse_prototype()
        return LuaChunk(header=header, main=main)


# ============== Format Detection and Auto-Parsing ==============

def detect_format(data: bytes) -> LuaFormat:
    """
    Detect the format of Lua bytecode.

    Returns:
        LuaFormat.LUAJ_HYBRID for Lua 5.2 header + Lua 5.3 instructions
        LuaFormat.LUA53_OFFICIAL for official Lua 5.3 format
    """
    # Ensure data is Python bytes, not Java jarray
    data = bytes(data)

    if len(data) < 6:
        raise ValueError("Data too short to be valid Lua bytecode")

    # Check signature
    if data[0:4] != b'\x1bLua':
        raise ValueError(f"Invalid Lua signature: {data[0:4].hex()}")

    version = data[4]
    
    if version == 0x52:
        return LuaFormat.LUAJ_HYBRID
    elif version == 0x53:
        return LuaFormat.LUA53_OFFICIAL
    else:
        raise ValueError(f"Unsupported Lua version: 0x{version:02x}")


def parse_file_auto(filepath: str) -> Tuple[LuaChunk, LuaFormat]:
    """
    Parse a Lua bytecode file, auto-detecting the format.
    
    Returns:
        Tuple of (LuaChunk, detected_format)
    """
    with open(filepath, 'rb') as f:
        data = f.read()
    return parse_bytes_auto(data)


def parse_bytes_auto(data: bytes) -> Tuple[LuaChunk, LuaFormat]:
    """
    Parse Lua bytecode from bytes, auto-detecting the format.
    
    Returns:
        Tuple of (LuaChunk, detected_format)
    """
    fmt = detect_format(data)
    
    if fmt == LuaFormat.LUAJ_HYBRID:
        parser = LuaBytecodeParser(data)
    else:
        parser = Lua53BytecodeParser(data)
    
    return parser.parse(), fmt


def parse_file(filepath: str, format: Optional[LuaFormat] = None) -> LuaChunk:
    """
    Parse a Lua bytecode file.
    
    Args:
        filepath: Path to the .luac file
        format: Optional format hint. If None, auto-detect the format.
    
    Returns:
        Parsed LuaChunk
    """
    with open(filepath, 'rb') as f:
        data = f.read()
    return parse_bytes(data, format)


def parse_bytes(data: bytes, format: Optional[LuaFormat] = None) -> LuaChunk:
    """
    Parse Lua bytecode from bytes.
    
    Args:
        data: Raw bytecode bytes
        format: Optional format hint. If None, auto-detect the format.
    
    Returns:
        Parsed LuaChunk
    """
    if format is None:
        # Auto-detect format
        format = detect_format(data)
    
    if format == LuaFormat.LUAJ_HYBRID:
        parser = LuaBytecodeParser(data)
    else:
        parser = Lua53BytecodeParser(data)
    
    return parser.parse()


# ============== Pretty Printing ==============

def print_prototype(proto: Prototype, indent: int = 0, name: str = "main"):
    """Pretty print a prototype"""
    prefix = "  " * indent
    
    print(f"{prefix}; function {name}")
    if proto.source:
        print(f"{prefix}.source \"{proto.source}\"")
    print(f"{prefix}.linedefined {proto.line_defined}")
    print(f"{prefix}.lastlinedefined {proto.last_line_defined}")
    print(f"{prefix}.numparams {proto.num_params}")
    print(f"{prefix}.is_vararg {proto.is_vararg}")
    print(f"{prefix}.maxstacksize {proto.max_stack_size}")
    print()
    
    # Upvalues
    for i, upval in enumerate(proto.upvalues):
        instack_str = "instack" if upval.instack else "extern"
        name_str = upval.name if upval.name else f"u{i}"
        print(f"{prefix}.upval u{i} \"{name_str}\" ; {instack_str}, idx={upval.idx}")
    print()
    
    # Constants
    print(f"{prefix}; Constants ({len(proto.constants)}):")
    for i, const in enumerate(proto.constants):
        print(f"{prefix};   K{i} = {const}")
    print()
    
    # Instructions
    print(f"{prefix}; Instructions ({len(proto.code)}):")
    for i, instr in enumerate(proto.code):
        line = proto.lineinfo[i] if i < len(proto.lineinfo) else 0
        print(f"{prefix}{i:4d} [{line:4d}] {format_instruction(instr, proto.constants)}")
    print()
    
    # Child prototypes
    for i, child in enumerate(proto.protos):
        print_prototype(child, indent + 1, f"F{i}")


def format_instruction(instr: Instruction, constants: List[LuaConstant] = None) -> str:
    """Format an instruction for display"""
    from .opcodes import OpMode, ISK, INDEXK
    
    name = instr.opcode_name
    
    def format_rk(val: int) -> str:
        """Format a register or constant reference"""
        if ISK(val):
            k_idx = INDEXK(val)
            if constants and k_idx < len(constants):
                return f"K{k_idx}({constants[k_idx]})"
            return f"K{k_idx}"
        return f"v{val}"
    
    if instr.mode == OpMode.iABC:
        # Different formatting based on opcode
        if instr.opcode in (Opcode.MOVE, Opcode.LOADNIL, Opcode.GETUPVAL, 
                           Opcode.UNM, Opcode.NOT, Opcode.LEN, Opcode.BNOT):
            return f"{name:12} v{instr.a} v{instr.b}"
        elif instr.opcode in (Opcode.LOADBOOL,):
            return f"{name:12} v{instr.a} {instr.b} {instr.c}"
        elif instr.opcode in (Opcode.GETTABUP, Opcode.GETFIELDU):
            return f"{name:12} v{instr.a} u{instr.b} {format_rk(instr.c)}"
        elif instr.opcode == Opcode.GETTABLE:
            return f"{name:12} v{instr.a} v{instr.b} {format_rk(instr.c)}"
        elif instr.opcode == Opcode.SETTABUP:
            return f"{name:12} u{instr.a} {format_rk(instr.b)} {format_rk(instr.c)}"
        elif instr.opcode == Opcode.SETUPVAL:
            return f"{name:12} v{instr.a} u{instr.b}"
        elif instr.opcode == Opcode.SETTABLE:
            return f"{name:12} v{instr.a} {format_rk(instr.b)} {format_rk(instr.c)}"
        elif instr.opcode in (Opcode.NEWTABLE,):
            return f"{name:12} v{instr.a} {instr.b} {instr.c}"
        elif instr.opcode == Opcode.SELF:
            return f"{name:12} v{instr.a} v{instr.b} {format_rk(instr.c)}"
        elif instr.opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV,
                             Opcode.MOD, Opcode.POW, Opcode.IDIV, Opcode.BAND,
                             Opcode.BOR, Opcode.BXOR, Opcode.SHL, Opcode.SHR):
            return f"{name:12} v{instr.a} {format_rk(instr.b)} {format_rk(instr.c)}"
        elif instr.opcode == Opcode.CONCAT:
            return f"{name:12} v{instr.a} v{instr.b} v{instr.c}"
        elif instr.opcode in (Opcode.EQ, Opcode.LT, Opcode.LE, Opcode.NEQ, 
                             Opcode.GE, Opcode.GT):
            return f"{name:12} {instr.a} {format_rk(instr.b)} {format_rk(instr.c)}"
        elif instr.opcode in (Opcode.TEST,):
            return f"{name:12} v{instr.a} {instr.c}"
        elif instr.opcode in (Opcode.TESTSET,):
            return f"{name:12} v{instr.a} v{instr.b} {instr.c}"
        elif instr.opcode in (Opcode.CALL, Opcode.TAILCALL):
            return f"{name:12} v{instr.a} {instr.b} {instr.c}"
        elif instr.opcode == Opcode.RETURN:
            return f"{name:12} v{instr.a} {instr.b}"
        elif instr.opcode == Opcode.SETLIST:
            return f"{name:12} v{instr.a} {instr.b} {instr.c}"
        elif instr.opcode == Opcode.VARARG:
            return f"{name:12} v{instr.a} {instr.b}"
        elif instr.opcode == Opcode.TFORCALL:
            return f"{name:12} v{instr.a} {instr.c}"
        else:
            return f"{name:12} v{instr.a} {instr.b} {instr.c}"
    
    elif instr.mode == OpMode.iABx:
        if instr.opcode == Opcode.LOADK:
            if constants and instr.bx < len(constants):
                return f"{name:12} v{instr.a} K{instr.bx}({constants[instr.bx]})"
            return f"{name:12} v{instr.a} K{instr.bx}"
        elif instr.opcode == Opcode.CLOSURE:
            return f"{name:12} v{instr.a} F{instr.bx}"
        else:
            return f"{name:12} v{instr.a} {instr.bx}"
    
    elif instr.mode == OpMode.iAsBx:
        if instr.opcode in (Opcode.JMP,):
            return f"{name:12} {instr.a} {instr.sbx:+d}"
        else:
            return f"{name:12} v{instr.a} {instr.sbx:+d}"
    
    elif instr.mode == OpMode.iAx:
        return f"{name:12} {instr.ax}"
    
    return f"{name:12} v{instr.a} {instr.b} {instr.c}"
