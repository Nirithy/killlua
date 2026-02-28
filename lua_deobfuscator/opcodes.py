"""
Lua 5.3 Opcode definitions for the LuaJ variant.
Based on refs/luaj/Lua.java
"""

from enum import IntEnum
from dataclasses import dataclass
from typing import Optional


class OpMode(IntEnum):
    """Instruction format modes"""
    iABC = 0   # A:8, B:9, C:9
    iABx = 1   # A:8, Bx:18
    iAsBx = 2  # A:8, sBx:18 (signed)
    iAx = 3    # Ax:26


class OpArgMask(IntEnum):
    """Operand usage types"""
    OpArgN = 0  # argument is not used
    OpArgU = 1  # argument is used
    OpArgR = 2  # argument is a register or a jump offset
    OpArgK = 3  # argument is a constant or register/constant


class Opcode(IntEnum):
    """Lua 5.3 Opcodes (LuaJ variant)"""
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
    DIV = 16
    MOD = 17
    POW = 18
    UNM = 19
    NOT = 20
    LEN = 21
    CONCAT = 22
    JMP = 23
    EQ = 24
    LT = 25
    LE = 26
    TEST = 27
    TESTSET = 28
    CALL = 29
    TAILCALL = 30
    RETURN = 31
    FORLOOP = 32
    FORPREP = 33
    TFORCALL = 34
    TFORLOOP = 35
    SETLIST = 36
    CLOSURE = 37
    VARARG = 38
    EXTRAARG = 39
    # Lua 5.3 extensions
    IDIV = 40
    BNOT = 41
    BAND = 42
    BOR = 43
    BXOR = 44
    SHL = 45
    SHR = 46
    # Custom LuaJ opcodes
    GETFIELDU = 47
    GETFIELDT = 48
    CLASS = 49
    # More custom opcodes (sparse)
    OR = 59
    AND = 60
    NEQ = 61
    GE = 62
    GT = 63


@dataclass
class OpcodeInfo:
    """Information about an opcode"""
    name: str
    mode: OpMode
    arg_b: OpArgMask
    arg_c: OpArgMask
    test_flag: bool  # operator is a test (next instruction must be a jump)
    set_a: bool      # instruction sets register A
    description: str


# Opcode information table
OPCODE_INFO = {
    Opcode.MOVE: OpcodeInfo("MOVE", OpMode.iABC, OpArgMask.OpArgR, OpArgMask.OpArgN, False, True, "R(A) := R(B)"),
    Opcode.LOADK: OpcodeInfo("LOADK", OpMode.iABx, OpArgMask.OpArgK, OpArgMask.OpArgN, False, True, "R(A) := K(Bx)"),
    Opcode.LOADKX: OpcodeInfo("LOADKX", OpMode.iABx, OpArgMask.OpArgN, OpArgMask.OpArgN, False, True, "R(A) := K(extra arg)"),
    Opcode.LOADBOOL: OpcodeInfo("LOADBOOL", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgU, False, True, "R(A) := (Bool)B; if (C) pc++"),
    Opcode.LOADNIL: OpcodeInfo("LOADNIL", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgN, False, True, "R(A), ..., R(A+B) := nil"),
    Opcode.GETUPVAL: OpcodeInfo("GETUPVAL", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgN, False, True, "R(A) := UpValue[B]"),
    Opcode.GETTABUP: OpcodeInfo("GETTABUP", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgK, False, True, "R(A) := UpValue[B][RK(C)]"),
    Opcode.GETTABLE: OpcodeInfo("GETTABLE", OpMode.iABC, OpArgMask.OpArgR, OpArgMask.OpArgK, False, True, "R(A) := R(B)[RK(C)]"),
    Opcode.SETTABUP: OpcodeInfo("SETTABUP", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, False, "UpValue[A][RK(B)] := RK(C)"),
    Opcode.SETUPVAL: OpcodeInfo("SETUPVAL", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgN, False, False, "UpValue[B] := R(A)"),
    Opcode.SETTABLE: OpcodeInfo("SETTABLE", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, False, "R(A)[RK(B)] := RK(C)"),
    Opcode.NEWTABLE: OpcodeInfo("NEWTABLE", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgU, False, True, "R(A) := {} (size B,C)"),
    Opcode.SELF: OpcodeInfo("SELF", OpMode.iABC, OpArgMask.OpArgR, OpArgMask.OpArgK, False, True, "R(A+1) := R(B); R(A) := R(B)[RK(C)]"),
    Opcode.ADD: OpcodeInfo("ADD", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "R(A) := RK(B) + RK(C)"),
    Opcode.SUB: OpcodeInfo("SUB", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "R(A) := RK(B) - RK(C)"),
    Opcode.MUL: OpcodeInfo("MUL", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "R(A) := RK(B) * RK(C)"),
    Opcode.DIV: OpcodeInfo("DIV", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "R(A) := RK(B) / RK(C)"),
    Opcode.MOD: OpcodeInfo("MOD", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "R(A) := RK(B) % RK(C)"),
    Opcode.POW: OpcodeInfo("POW", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "R(A) := RK(B) ^ RK(C)"),
    Opcode.UNM: OpcodeInfo("UNM", OpMode.iABC, OpArgMask.OpArgR, OpArgMask.OpArgN, False, True, "R(A) := -R(B)"),
    Opcode.NOT: OpcodeInfo("NOT", OpMode.iABC, OpArgMask.OpArgR, OpArgMask.OpArgN, False, True, "R(A) := not R(B)"),
    Opcode.LEN: OpcodeInfo("LEN", OpMode.iABC, OpArgMask.OpArgR, OpArgMask.OpArgN, False, True, "R(A) := length of R(B)"),
    Opcode.CONCAT: OpcodeInfo("CONCAT", OpMode.iABC, OpArgMask.OpArgR, OpArgMask.OpArgR, False, True, "R(A) := R(B).. ... ..R(C)"),
    Opcode.JMP: OpcodeInfo("JMP", OpMode.iAsBx, OpArgMask.OpArgR, OpArgMask.OpArgN, False, False, "pc += sBx; if (A) close upvalues >= R(A-1)"),
    Opcode.EQ: OpcodeInfo("EQ", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, True, False, "if ((RK(B) == RK(C)) ~= A) then pc++"),
    Opcode.LT: OpcodeInfo("LT", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, True, False, "if ((RK(B) < RK(C)) ~= A) then pc++"),
    Opcode.LE: OpcodeInfo("LE", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, True, False, "if ((RK(B) <= RK(C)) ~= A) then pc++"),
    Opcode.TEST: OpcodeInfo("TEST", OpMode.iABC, OpArgMask.OpArgN, OpArgMask.OpArgU, True, False, "if not (R(A) <=> C) then pc++"),
    Opcode.TESTSET: OpcodeInfo("TESTSET", OpMode.iABC, OpArgMask.OpArgR, OpArgMask.OpArgU, True, True, "if (R(B) <=> C) then R(A) := R(B) else pc++"),
    Opcode.CALL: OpcodeInfo("CALL", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgU, False, True, "R(A), ..., R(A+C-2) := R(A)(R(A+1), ..., R(A+B-1))"),
    Opcode.TAILCALL: OpcodeInfo("TAILCALL", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgU, False, True, "return R(A)(R(A+1), ..., R(A+B-1))"),
    Opcode.RETURN: OpcodeInfo("RETURN", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgN, False, False, "return R(A), ..., R(A+B-2)"),
    Opcode.FORLOOP: OpcodeInfo("FORLOOP", OpMode.iAsBx, OpArgMask.OpArgR, OpArgMask.OpArgN, False, True, "R(A)+=R(A+2); if R(A) <?= R(A+1) then { pc+=sBx; R(A+3)=R(A) }"),
    Opcode.FORPREP: OpcodeInfo("FORPREP", OpMode.iAsBx, OpArgMask.OpArgR, OpArgMask.OpArgN, False, True, "R(A)-=R(A+2); pc+=sBx"),
    Opcode.TFORCALL: OpcodeInfo("TFORCALL", OpMode.iABC, OpArgMask.OpArgN, OpArgMask.OpArgU, False, False, "R(A+3), ..., R(A+2+C) := R(A)(R(A+1), R(A+2))"),
    Opcode.TFORLOOP: OpcodeInfo("TFORLOOP", OpMode.iAsBx, OpArgMask.OpArgR, OpArgMask.OpArgN, False, True, "if R(A+1) ~= nil then { R(A)=R(A+1); pc += sBx }"),
    Opcode.SETLIST: OpcodeInfo("SETLIST", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgU, False, False, "R(A)[(C-1)*FPF+i] := R(A+i), 1 <= i <= B"),
    Opcode.CLOSURE: OpcodeInfo("CLOSURE", OpMode.iABx, OpArgMask.OpArgU, OpArgMask.OpArgN, False, True, "R(A) := closure(KPROTO[Bx])"),
    Opcode.VARARG: OpcodeInfo("VARARG", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgN, False, True, "R(A), R(A+1), ..., R(A+B-2) = vararg"),
    Opcode.EXTRAARG: OpcodeInfo("EXTRAARG", OpMode.iAx, OpArgMask.OpArgU, OpArgMask.OpArgU, False, False, "extra (larger) argument for previous opcode"),
    # Lua 5.3 extensions
    Opcode.IDIV: OpcodeInfo("IDIV", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "R(A) := RK(B) // RK(C)"),
    Opcode.BNOT: OpcodeInfo("BNOT", OpMode.iABC, OpArgMask.OpArgR, OpArgMask.OpArgN, False, True, "R(A) := ~R(B)"),
    Opcode.BAND: OpcodeInfo("BAND", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "R(A) := RK(B) & RK(C)"),
    Opcode.BOR: OpcodeInfo("BOR", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "R(A) := RK(B) | RK(C)"),
    Opcode.BXOR: OpcodeInfo("BXOR", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "R(A) := RK(B) ~ RK(C)"),
    Opcode.SHL: OpcodeInfo("SHL", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "R(A) := RK(B) << RK(C)"),
    Opcode.SHR: OpcodeInfo("SHR", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "R(A) := RK(B) >> RK(C)"),
    # Custom LuaJ opcodes
    Opcode.GETFIELDU: OpcodeInfo("GETFIELDU", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgK, False, True, "R(A) := UpValue[B][RK(C)]"),
    Opcode.GETFIELDT: OpcodeInfo("GETFIELDT", OpMode.iABC, OpArgMask.OpArgR, OpArgMask.OpArgK, False, True, "Custom GETFIELDT"),
    Opcode.CLASS: OpcodeInfo("CLASS", OpMode.iABC, OpArgMask.OpArgU, OpArgMask.OpArgU, False, True, "Custom CLASS"),
    Opcode.OR: OpcodeInfo("OR", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "Custom OR"),
    Opcode.AND: OpcodeInfo("AND", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, False, True, "Custom AND"),
    Opcode.NEQ: OpcodeInfo("NEQ", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, True, False, "Custom NEQ - if ((RK(B) ~= RK(C)) ~= A) then pc++"),
    Opcode.GE: OpcodeInfo("GE", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, True, False, "Custom GE - if ((RK(B) >= RK(C)) ~= A) then pc++"),
    Opcode.GT: OpcodeInfo("GT", OpMode.iABC, OpArgMask.OpArgK, OpArgMask.OpArgK, True, False, "Custom GT - if ((RK(B) > RK(C)) ~= A) then pc++"),
}


def get_opcode_name(opcode: int) -> str:
    """Get the name of an opcode"""
    try:
        return Opcode(opcode).name
    except ValueError:
        return f"UNKNOWN_{opcode}"


def get_opcode_info(opcode: int) -> Optional[OpcodeInfo]:
    """Get information about an opcode"""
    try:
        return OPCODE_INFO.get(Opcode(opcode))
    except ValueError:
        return None


def get_opcode_mode(opcode: int) -> OpMode:
    """Get the instruction mode for an opcode"""
    info = get_opcode_info(opcode)
    if info:
        return info.mode
    return OpMode.iABC  # Default


# Instruction field sizes
SIZE_OP = 6
SIZE_A = 8
SIZE_B = 9
SIZE_C = 9
SIZE_Bx = SIZE_B + SIZE_C  # 18
SIZE_Ax = SIZE_A + SIZE_B + SIZE_C  # 26

# Instruction field positions
POS_OP = 0
POS_A = SIZE_OP  # 6
POS_C = POS_A + SIZE_A  # 14
POS_B = POS_C + SIZE_C  # 23
POS_Bx = POS_C  # 14
POS_Ax = POS_A  # 6

# Masks
MASK_OP = (1 << SIZE_OP) - 1  # 0x3F
MASK_A = (1 << SIZE_A) - 1    # 0xFF
MASK_B = (1 << SIZE_B) - 1    # 0x1FF
MASK_C = (1 << SIZE_C) - 1    # 0x1FF
MASK_Bx = (1 << SIZE_Bx) - 1  # 0x3FFFF
MASK_Ax = (1 << SIZE_Ax) - 1  # 0x3FFFFFF

# Maximum values
MAXARG_A = MASK_A
MAXARG_B = MASK_B
MAXARG_C = MASK_C
MAXARG_Bx = MASK_Bx
MAXARG_sBx = MAXARG_Bx >> 1  # 131071

# RK (Register/Constant) bit
BITRK = 1 << (SIZE_B - 1)  # 256
MAXINDEXRK = BITRK - 1     # 255

# Fields per flush for SETLIST
LFIELDS_PER_FLUSH = 50


def ISK(x: int) -> bool:
    """Check if x is a constant index"""
    return (x & BITRK) != 0


def INDEXK(x: int) -> int:
    """Get constant index from RK value"""
    return x & ~BITRK


def RKASK(x: int) -> int:
    """Convert constant index to RK value"""
    return x | BITRK
