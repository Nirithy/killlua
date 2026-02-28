# Lua Deobfuscator Package
# A Python-based deobfuscation tool for Lua 5.2 Header + Lua 5.3 Instructions format

__version__ = "0.1.0"

from .parser import (
    parse_file,
    parse_bytes,
    LuaChunk,
    LuaHeader,
    Prototype,
    Instruction,
    LuaConstant,
    LuaConstantType,
    Upvalue,
    LocVar,
)

from .serializer import (
    serialize_chunk,
    serialize_file,
    LuaBytecodeSerializer,
    create_default_header,
    chunk_from_prototype,
    verify_round_trip,
    verify_round_trip_file,
    compare_prototypes,
    recalculate_jumps,
    update_instruction_raw,
)

from .deobfuscator import (
    Deobfuscator,
    DeobfuscationPass,
    DeadCodeEliminator,
    ConstantFolder,
    DeadBranchEliminator,
    SequentialBlockMerger,
    DeobfuscationResult,
    deobfuscate,
    deobfuscate_all,
)

__all__ = [
    # Version
    "__version__",
    # Parser
    "parse_file",
    "parse_bytes",
    "LuaChunk",
    "LuaHeader",
    "Prototype",
    "Instruction",
    "LuaConstant",
    "LuaConstantType",
    "Upvalue",
    "LocVar",
    # Serializer
    "serialize_chunk",
    "serialize_file",
    "LuaBytecodeSerializer",
    "create_default_header",
    "chunk_from_prototype",
    "verify_round_trip",
    "verify_round_trip_file",
    "compare_prototypes",
    "recalculate_jumps",
    "update_instruction_raw",
    # Deobfuscator
    "Deobfuscator",
    "DeobfuscationPass",
    "DeadCodeEliminator",
    "ConstantFolder",
    "DeadBranchEliminator",
    "SequentialBlockMerger",
    "DeobfuscationResult",
    "deobfuscate",
    "deobfuscate_all",
]
