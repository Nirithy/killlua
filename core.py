

from typing import Dict, List, Optional, Any
import struct

from lua_deobfuscator import parse_bytes, serialize_chunk
from lua_deobfuscator.parser import (
    detect_format, LuaFormat, LuaChunk, Prototype, Instruction,
    LuaConstant, LuaConstantType, Upvalue, LocVar
)
from lua_deobfuscator.disassembler import Disassembler, disassemble_prototype
from lua_deobfuscator.opcodes import Opcode, OpMode, ISK, INDEXK, get_opcode_name
from lua_deobfuscator.cfg import build_cfg, build_cfg_for_closure
from lua_deobfuscator.deobfuscator import (
    Deobfuscator, DeobfuscationPass,
    DeadCodeEliminator, ConstantFolder,
    DeadBranchEliminator, SequentialBlockMerger
)


# Lua signature
LUA_SIGNATURE = b'\x1bLua'


def parse_hybrid(lua_bytes: bytes) -> dict:
    """
    解析 hybrid 格式字节码

    Args:
        lua_bytes: Hybrid 格式 Lua 字节码

    Returns:
        包含解析结果的字典:
        {
            'success': bool,
            'chunk': dict,  # 序列化的 LuaChunk
            'format': str,  # 'hybrid' 或 'lua53'
            'error': str    # 失败时的错误信息
        }
    """
    try:
        # Detect format
        fmt = detect_format(lua_bytes)
        format_str = 'hybrid' if fmt == LuaFormat.LUAJ_HYBRID else 'lua53'

        # Parse the bytecode
        chunk = parse_bytes(lua_bytes)

        # Serialize chunk to dict for return
        chunk_dict = _chunk_to_dict(chunk)

        return {
            'success': True,
            'chunk': chunk_dict,
            'format': format_str,
            'error': None
        }
    except Exception as e:
        return {
            'success': False,
            'chunk': None,
            'format': 'unknown',
            'error': str(e)
        }


def disassemble_to_lasm(lua_bytes: bytes, closure_path: str = None) -> dict:
    """
    反汇编为 .lasm 格式

    Args:
        lua_bytes: Hybrid 格式 Lua 字节码
        closure_path: 闭包路径 (如 "F0", "F0/1"), 为 None 则反汇编全部

    Returns:
        {
            'success': bool,
            'lasm': str,    # .lasm 格式文本
            'closures': list,  # 闭包列表信息
            'error': str
        }
    """
    try:
        # Parse the bytecode
        chunk = parse_bytes(lua_bytes)

        # Get closures list
        closures = _list_closures(chunk.main)

        # Disassemble using Disassembler class
        disasm = Disassembler(chunk)
        lasm_text = disasm.disassemble(closure_path, include_children=True)

        return {
            'success': True,
            'lasm': lasm_text,
            'closures': closures,
            'error': None
        }
    except Exception as e:
        return {
            'success': False,
            'lasm': '',
            'closures': [],
            'error': str(e)
        }


def get_info(lua_bytes: bytes) -> dict:
    """
    获取 Lua 文件信息

    Returns:
        {
            'valid': bool,
            'version': str,
            'format': str,
            'size': int,
            'closures_count': int,
            'constants_count': int,
            'variant': str  # 'standard', 'elgg', 'rlgg', 'wsg_pro'
        }
    """
    result = {
        'valid': False,
        'version': 'unknown',
        'format': 'unknown',
        'size': len(lua_bytes),
        'closures_count': 0,
        'constants_count': 0,
        'variant': 'unknown'
    }

    try:
        # Check signature
        if len(lua_bytes) < 4:
            result['error'] = 'File too small'
            return result

        if lua_bytes[:4] != LUA_SIGNATURE:
            result['error'] = 'Invalid Lua signature'
            return result

        result['valid'] = True

        # Detect version
        if len(lua_bytes) >= 5:
            version_byte = lua_bytes[4]
            if version_byte == 0x52:
                result['version'] = '5.2'
                result['format'] = 'hybrid'
            elif version_byte == 0x53:
                result['version'] = '5.3'
                result['format'] = 'lua53'
            else:
                result['version'] = f'unknown (0x{version_byte:02X})'

        # Detect variant
        result['variant'] = _detect_variant(lua_bytes)

        # Parse to get counts
        try:
            chunk = parse_bytes(lua_bytes)
            result['closures_count'] = _count_closures(chunk.main)
            result['constants_count'] = len(chunk.main.constants)
        except:
            pass

    except Exception as e:
        result['error'] = str(e)

    return result


def serialize_to_hybrid(chunk_dict: dict) -> bytes:
    """
    将 LuaChunk 序列化为 hybrid 格式

    Args:
        chunk_dict: 序列化的 LuaChunk 字典

    Returns:
        Hybrid 格式字节码
    """
    # Convert dict back to chunk
    chunk = _dict_to_chunk(chunk_dict)

    # Serialize to hybrid format
    return serialize_chunk(chunk)


def get_closure_list(lua_bytes: bytes) -> dict:
    """
    获取所有闭包列表

    Returns:
        {
            'success': bool,
            'closures': list,  # List of dicts with closure info
            'error': str       # Error message if failed
        }
        Closure info format:
        {
            'id': str,        # e.g., 'F0', 'F1'
            'path': str,      # e.g., 'F0', 'F0/1'
            'name': str,      # Function name or 'anonymous'
            'line_defined': int,
            'num_params': int,
            'num_instructions': int
        }
    """
    try:
        chunk = parse_bytes(lua_bytes)
        closures = _list_closures(chunk.main)
        return {
            'success': True,
            'closures': closures,
            'error': None,
            'count': len(closures)
        }
    except Exception as e:
        import traceback
        return {
            'success': False,
            'closures': [],
            'error': str(e),
            'traceback': traceback.format_exc()
        }


# ============== Helper Functions ==============

def _chunk_to_dict(chunk: LuaChunk) -> dict:
    """Convert LuaChunk to dictionary"""
    return {
        'header': _header_to_dict(chunk.header),
        'main': _prototype_to_dict(chunk.main)
    }


def _header_to_dict(header) -> dict:
    """Convert LuaHeader to dictionary"""
    # Handle both Python bytes and Java byte arrays (jarray)
    sig = header.signature
    tail = header.tail

    # Convert to bytes if it's a sequence of integers (Java byte array)
    if hasattr(sig, '__iter__') and not isinstance(sig, (str, bytes)):
        try:
            sig = bytes(sig)
        except:
            pass
    if hasattr(tail, '__iter__') and not isinstance(tail, (str, bytes)):
        try:
            tail = bytes(tail)
        except:
            pass

    return {
        'signature': sig.hex() if isinstance(sig, bytes) else str(sig),
        'version': header.version,
        'format': header.format,
        'endianness': header.endianness,
        'size_int': header.size_int,
        'size_size_t': header.size_size_t,
        'size_instruction': header.size_instruction,
        'size_lua_number': header.size_lua_number,
        'integral_flag': header.integral_flag,
        'tail': tail.hex() if isinstance(tail, bytes) else str(tail)
    }


def _prototype_to_dict(proto: Prototype) -> dict:
    """Convert Prototype to dictionary"""
    return {
        'source': proto.source,
        'line_defined': proto.line_defined,
        'last_line_defined': proto.last_line_defined,
        'num_params': proto.num_params,
        'is_vararg': proto.is_vararg,
        'max_stack_size': proto.max_stack_size,
        'code': [_instruction_to_dict(instr) for instr in proto.code],
        'constants': [_constant_to_dict(c) for c in proto.constants],
        'protos': [_prototype_to_dict(p) for p in proto.protos],
        'upvalues': [_upvalue_to_dict(u) for u in proto.upvalues],
        'lineinfo': proto.lineinfo,
        'locvars': [_locvar_to_dict(l) for l in proto.locvars]
    }


def _instruction_to_dict(instr: Instruction) -> dict:
    """Convert Instruction to dictionary"""
    return {
        'raw': instr.raw,
        'opcode': instr.opcode,
        'opcode_name': instr.opcode_name,
        'a': instr.a,
        'b': instr.b,
        'c': instr.c,
        'bx': instr.bx,
        'sbx': instr.sbx,
        'ax': instr.ax,
        'mode': instr.mode.value if hasattr(instr.mode, 'value') else int(instr.mode)
    }


def _constant_to_dict(const: LuaConstant) -> dict:
    """Convert LuaConstant to dictionary"""
    return {
        'type': const.type.value if hasattr(const.type, 'value') else int(const.type),
        'type_name': const.type.name if hasattr(const.type, 'name') else str(const.type),
        'value': const.value
    }


def _upvalue_to_dict(upval: Upvalue) -> dict:
    """Convert Upvalue to dictionary"""
    return {
        'name': upval.name,
        'instack': upval.instack,
        'idx': upval.idx
    }


def _locvar_to_dict(locvar: LocVar) -> dict:
    """Convert LocVar to dictionary"""
    return {
        'varname': locvar.varname,
        'startpc': locvar.startpc,
        'endpc': locvar.endpc
    }


def _dict_to_chunk(d: dict) -> LuaChunk:
    """Convert dictionary to LuaChunk"""
    from lua_deobfuscator.parser import LuaHeader, Prototype

    header = LuaHeader(
        signature=bytes.fromhex(d['header']['signature']) if isinstance(d['header']['signature'], str) else d['header']['signature'],
        version=d['header']['version'],
        format=d['header']['format'],
        endianness=d['header']['endianness'],
        size_int=d['header']['size_int'],
        size_size_t=d['header']['size_size_t'],
        size_instruction=d['header']['size_instruction'],
        size_lua_number=d['header']['size_lua_number'],
        integral_flag=d['header']['integral_flag'],
        tail=bytes.fromhex(d['header']['tail']) if isinstance(d['header']['tail'], str) else d['header']['tail']
    )

    main = _dict_to_prototype(d['main'])

    return LuaChunk(header=header, main=main)


def _dict_to_prototype(d: dict) -> Prototype:
    """Convert dictionary to Prototype"""
    from lua_deobfuscator.parser import Prototype, Instruction, LuaConstant, Upvalue, LocVar, LuaConstantType

    code = []
    for instr_dict in d['code']:
        code.append(Instruction(
            raw=instr_dict['raw'],
            opcode=instr_dict['opcode'],
            opcode_name=instr_dict['opcode_name'],
            a=instr_dict['a'],
            b=instr_dict['b'],
            c=instr_dict['c'],
            bx=instr_dict['bx'],
            sbx=instr_dict['sbx'],
            ax=instr_dict['ax'],
            mode=OpMode(instr_dict['mode']) if isinstance(instr_dict['mode'], int) else instr_dict['mode']
        ))

    constants = []
    for const_dict in d['constants']:
        const_type = const_dict['type']
        if isinstance(const_type, int):
            const_type = LuaConstantType(const_type)
        constants.append(LuaConstant(type=const_type, value=const_dict['value']))

    upvalues = [Upvalue(name=u['name'], instack=u['instack'], idx=u['idx']) for u in d['upvalues']]
    locvars = [LocVar(varname=l['varname'], startpc=l['startpc'], endpc=l['endpc']) for l in d['locvars']]
    protos = [_dict_to_prototype(p) for p in d['protos']]

    return Prototype(
        source=d['source'],
        line_defined=d['line_defined'],
        last_line_defined=d['last_line_defined'],
        num_params=d['num_params'],
        is_vararg=d['is_vararg'],
        max_stack_size=d['max_stack_size'],
        code=code,
        constants=constants,
        protos=protos,
        upvalues=upvalues,
        lineinfo=d['lineinfo'],
        locvars=locvars
    )


def _count_closures(proto: Prototype) -> int:
    """Count total closures in a prototype"""
    count = len(proto.protos)
    for child in proto.protos:
        count += _count_closures(child)
    return count


def _list_closures(proto: Prototype) -> List[dict]:
    """List all closures with their info - including main function

    Generates both linear IDs (F0, F1, F2...) for UI display and
    nested paths (F0, F0/1, F0/1/1...) for disassembly parameters.

    Path format follows ClosurePath.parse() convention:
    - First level: 0-based (F0, F1, F2...)
    - Nested levels: 1-based (F0/1, F0/2...)

    ClosurePath.parse() converts:
    - F0 -> path [0] (first level, 0-based)
    - F0/1 -> path [0, 0] (nested level, converts 1 to 0-based internally)
    - F1/2 -> path [1, 1] (first level F1=[1], nested 2 converts to [1])
    """
    result = []

    # Add main function first - both id and path are 'main'
    result.append({
        'id': 'main',
        'path': 'main',
        'name': proto.source if proto.source else 'main',
        'line_defined': proto.line_defined,
        'num_params': proto.num_params,
        'num_instructions': len(proto.code),
        'depth': 0
    })

    # Use recursion to generate closures matching the disassembler's numbering
    # The disassembler uses pre-order DFS with global counter
    func_counter = [0]  # Use list for mutable reference

    def process_children(parent_proto: Prototype, parent_display_path: str, depth: int):
        """Process children of a prototype recursively

        Args:
            parent_proto: The parent prototype whose children to process
            parent_display_path: The display path for the parent (e.g., 'main', 'F0', 'F0/1')
            depth: The nesting depth (1 for direct children of main)
        """
        nonlocal result

        n = len(parent_proto.protos)
        if n == 0:
            return

        offset = func_counter[0]
        func_counter[0] += n

        for i, child in enumerate(parent_proto.protos):
            func_num = offset + i

            # Generate nested path string following lasm convention
            # First level (depth=1, children of main): F0, F1, F2... (0-based)
            # Nested levels (depth>1): F0/1, F0/2, F0/1/1... (nested uses 1-based)
            if parent_display_path == 'main':
                # Direct child of main: F0, F1, F2... (0-based)
                nested_path = f"F{i}"
            else:
                # Nested child: append 1-based index
                # ClosurePath.parse() will convert back to 0-based internally
                nested_path = f"{parent_display_path}/{i + 1}"

            func_id = f"F{func_num}"

            result.append({
                'id': func_id,
                'path': nested_path,
                'name': child.source if child.source else 'anonymous',
                'line_defined': child.line_defined,
                'num_params': child.num_params,
                'num_instructions': len(child.code),
                'depth': depth
            })

            # Recursively process grandchildren
            process_children(child, nested_path, depth + 1)

    # Process all children starting from main (depth 1 for direct children)
    process_children(proto, 'main', 1)

    return result


def _detect_variant(lua_bytes: bytes) -> str:
    """Detect GameGuardian variant"""
    if len(lua_bytes) < 4:
        return "invalid"

    if lua_bytes[:4] != LUA_SIGNATURE:
        return "unknown"

    # Check for specific patterns in header
    if len(lua_bytes) > 100:
        header_section = lua_bytes[4:min(50, len(lua_bytes))]

        if b'ELGG' in header_section:
            return "elgg"
        if b'RLGG' in header_section:
            return "rlgg"
        if b'WSG' in header_section:
            return "wsg_pro"

    return "standard"


# ============== Compatibility with old lua_processor ==============

def disassemble(lua_bytes: bytes) -> str:
    """Legacy disassemble function for compatibility"""
    result = disassemble_to_lasm(lua_bytes)
    if result['success']:
        return result['lasm']
    error_msg = result.get('error', 'Unknown error')
    return "Error: " + str(error_msg)


def analyze_structure(lua_bytes: bytes) -> Dict:
    """Legacy analyze_structure function for compatibility"""
    return get_info(lua_bytes)


def detect_gg_variant(lua_bytes: bytes) -> str:
    """Legacy detect_gg_variant function for compatibility"""
    return _detect_variant(lua_bytes)


def get_info_str(lua_bytes: bytes) -> str:
    """Get human-readable information about a Lua file"""
    info = get_info(lua_bytes)

    lines = []
    lines.append("=" * 50)
    lines.append("Lua File Analysis")
    lines.append("=" * 50)
    valid_str = 'Yes' if info['valid'] else 'No'
    lines.append(f"Valid Lua: {valid_str}")
    lines.append("Version: " + str(info.get('version')))
    lines.append("Format: " + str(info.get('format')))
    lines.append("Size: " + str(info.get('size')) + " bytes")
    lines.append("Variant: " + str(info.get('variant')))
    lines.append("Closures: " + str(info.get('closures_count')))
    lines.append("Constants: " + str(info.get('constants_count')))

    err = info.get('error')
    if err:
        lines.append("")
        lines.append("Error: " + str(err))

    return '\n'.join(lines)


def test():
    """Test function to verify the module is working"""
    import sys
    test_bytes = b'\x1bLua\x52\x00\x01\x04\x04\x04\x08\x00\x19\x93\r\n\x1a\n'
    info = get_info(test_bytes)
    return {
        'python_version': sys.version,
        'module': 'lua_helper_core',
        'test_result': info,
        'status': 'OK' if info['valid'] else 'FAIL'
    }


# ============== Local Deobfuscation Interface ==============

def local_deobfuscate(
    lua_bytes: bytes,
    passes,
    auth_code: str,
    device_id: str
) -> dict:
    """
    本地执行反混淆处理

    Args:
        lua_bytes: Lua字节码
        passes: 要执行的Pass列表（Python list）
        auth_code: 用户卡密
        device_id: 设备ID

    Returns:
        {
            'success': bool,
            'output_bytes': bytes,  # 处理后的字节码
            'results': [            # 各Pass处理结果
                {
                    'pass_name': str,      # 纯pass名称
                    'closure_path': str,   # closure路径，如 "main", "F0", "F0/1"
                    'changes_made': int,
                    'details': str
                }
            ],
            'total_changes': int,
            'error_message': str
        }
    """
    try:
        # 1. 解析字节码
        chunk = parse_bytes(lua_bytes)

        # 2. 执行各Pass（递归处理所有函数原型）
        results = []
        total_changes = 0

        # 处理主函数及其所有子函数
        def process_prototype(proto, path="main"):
            nonlocal total_changes

            # 创建反混淆器
            deob = Deobfuscator(proto)

            # 执行每个选定的Pass
            for pass_name in passes:
                result = _run_deobfuscation_pass(deob, pass_name)
                results.append({
                    'pass_name': pass_name,  # 纯pass名称
                    'closure_path': path,    # closure路径
                    'changes_made': result['changes_made'],
                    'details': result.get('details', '')
                })
                total_changes += result['changes_made']

            # 递归处理子函数
            for i, child_proto in enumerate(proto.protos):
                process_prototype(child_proto, f"{path}.F{i}")

        # 从主函数开始处理
        process_prototype(chunk.main)

        # 3. 序列化输出
        output_bytes = serialize_chunk(chunk)

        return {
            'success': True,
            'output_bytes': output_bytes,
            'results': results,
            'total_changes': total_changes,
            'error_message': ''
        }

    except Exception as e:
        import traceback
        return {
            'success': False,
            'output_bytes': None,
            'results': [],
            'total_changes': 0,
            'error_message': str(e),
            'traceback': traceback.format_exc()
        }


def _run_deobfuscation_pass(deob: Deobfuscator, pass_name: str) -> dict:
    """执行单个反混淆Pass"""

    pass_map = {
        'constant_folding': DeobfuscationPass.CONSTANT_FOLDING,
        'dead_branch_elimination': DeobfuscationPass.DEAD_BRANCH_ELIMINATION,
        'sequential_block_merge': DeobfuscationPass.SEQUENTIAL_BLOCK_MERGE,
        'dead_code_elimination': DeobfuscationPass.DEAD_CODE_ELIMINATION
    }

    pass_enum = pass_map.get(pass_name)
    if not pass_enum:
        return {'changes_made': 0, 'details': f'Unknown pass: {pass_name}'}

    result = deob.run_pass(pass_enum)

    return {
        'changes_made': result.changes_made,
        'details': result.details
    }


# ============== Closure Serialization for GG Disassembler ==============

def serialize_closure_to_luac(lua_bytes: bytes, closure_path: str = None) -> dict:
    """
    将指定的 closure 序列化为 luac 字节码

    Args:
        lua_bytes: 原始 Lua 文件字节
        closure_path: closure 路径 (如 "main", "F0", "F0/1")，为 None 则使用 main

    Returns:
        dict: {
            "success": bool,
            "luac_bytes": bytes or None,
            "error": str or None
        }
    """
    try:
        from lua_deobfuscator import parse_bytes, chunk_from_prototype, serialize_chunk

        # 解析原始文件
        chunk = parse_bytes(lua_bytes)

        # 根据路径查找目标 prototype
        if closure_path is None or closure_path == "main":
            target_proto = chunk.main
        else:
            # 解析路径 "F0/F1" -> [0, 1]
            # 注意：第一层是 0-based (F0, F1...)，嵌套层是 1-based (F0/1, F0/2...)
            indices = []
            parts = closure_path.split('/')

            for i, part in enumerate(parts):
                if i == 0:
                    # 第一层：必须是 F0, F1, F2... 格式，0-based
                    if not part.startswith('F'):
                        return {"success": False, "luac_bytes": None, "error": f"Invalid path: {closure_path}"}
                    try:
                        idx = int(part[1:])
                        indices.append(idx)
                    except ValueError:
                        return {"success": False, "luac_bytes": None, "error": f"Invalid path segment: {part}"}
                else:
                    # 嵌套层：1, 2, 3... 格式，1-based，需要减1转为 0-based
                    try:
                        idx = int(part)
                        indices.append(idx - 1)
                    except ValueError:
                        return {"success": False, "luac_bytes": None, "error": f"Invalid path segment: {part}"}

            # 遍历查找
            target_proto = chunk.main
            for idx in indices:
                if idx < 0 or idx >= len(target_proto.protos):
                    return {"success": False, "luac_bytes": None, "error": f"Index out of range: {idx} in path {closure_path}"}
                target_proto = target_proto.protos[idx]

        # 创建新的 chunk（只包含目标 prototype）
        new_chunk = chunk_from_prototype(target_proto, chunk.header)

        # 序列化为字节
        luac_bytes = serialize_chunk(new_chunk)

        return {
            "success": True,
            "luac_bytes": luac_bytes,
            "error": None
        }

    except Exception as e:
        import traceback
        return {
            "success": False,
            "luac_bytes": None,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# ============== CFG Visualization Interface ==============

def generate_cfg_for_api(lua_bytes: bytes, closure_paths: list, base_name: str) -> dict:
    """
    生成 CFG DOT 内容，供 Android 层调用在线 API 渲染

    Args:
        lua_bytes: Hybrid 格式 Lua 字节码
        closure_paths: 闭包路径列表 (如 ["main", "F0", "F0/1"])
        base_name: 基础文件名（用于生成文件名）

    Returns:
        {
            'success': bool,
            'dot_files': List[{
                'closure_id': str,
                'closure_path': str,
                'dot_content': str,   # DOT 内容字符串
                'dot_filename': str   # 建议的 DOT 文件名
            }],
            'output_dir': str,  # PNG 输出目录路径
            'error': str
        }
    """
    import os

    # PNG 输出目录（Android 层会保存到这里）
    png_dir = "/sdcard/Download/LuaHelper/CFG_PNG"
    dot_dir = "/sdcard/Download/LuaHelper/CFG_DOT"

    os.makedirs(png_dir, exist_ok=True)
    os.makedirs(dot_dir, exist_ok=True)

    try:
        chunk = parse_bytes(lua_bytes)
        results = []

        for closure_path in closure_paths:
            closure_id = _get_linear_id(closure_path, chunk)

            # 构建 CFG
            cfg = build_cfg_for_closure(chunk, closure_path)

            # 生成 DOT 内容
            dot_content = cfg.to_dot(include_instructions=True)

            # 保存 DOT 文件到本地
            dot_filename = f"{base_name}.{closure_id}.dot"
            dot_path = os.path.join(dot_dir, dot_filename)
            cfg.save_dot(dot_path, include_instructions=True)

            results.append({
                'closure_id': closure_id,
                'closure_path': closure_path,
                'dot_content': dot_content,
                'dot_filename': dot_filename,
                'dot_path': dot_path,
                'png_filename': f"{base_name}.{closure_id}.png"
            })

        return {
            'success': True,
            'dot_files': results,
            'output_dir': png_dir,
            'error': None
        }

    except Exception as e:
        import traceback
        return {
            'success': False,
            'dot_files': [],
            'output_dir': png_dir,
            'error': str(e),
            'traceback': traceback.format_exc()
        }


def generate_cfg_png(lua_bytes: bytes, closure_paths: list, base_name: str) -> dict:
    """
    生成 CFG DOT 内容，供 Android 层调用在线 API 渲染为 PNG

    Args:
        lua_bytes: Hybrid 格式 Lua 字节码
        closure_paths: 闭包路径列表 (如 ["main", "F0", "F0/1"])
        base_name: 基础文件名（用于生成文件名）

    Returns:
        {
            'success': bool,
            'dot_files': List[{
                'closure_id': str,
                'closure_path': str,
                'dot_content': str,   # DOT 内容字符串（供API使用）
                'dot_path': str,      # DOT 文件本地保存路径
                'png_filename': str   # 建议的 PNG 文件名
            }],
            'png_output_dir': str,  # PNG 输出目录（Android层保存到这里）
            'error': str
        }
    """
    import os

    dot_dir = "/sdcard/Download/LuaHelper/CFG_DOT"
    png_dir = "/sdcard/Download/LuaHelper/CFG_PNG"

    try:
        # 创建目录
        os.makedirs(dot_dir, exist_ok=True)
        os.makedirs(png_dir, exist_ok=True)
    except Exception as e:
        # 如果创建失败，使用应用私有目录
        import tempfile
        dot_dir = os.path.join(tempfile.gettempdir(), "CFG_DOT")
        png_dir = os.path.join(tempfile.gettempdir(), "CFG_PNG")
        os.makedirs(dot_dir, exist_ok=True)
        os.makedirs(png_dir, exist_ok=True)

    try:
        # 检查输入
        if not lua_bytes or len(lua_bytes) == 0:
            return {
                'success': False,
                'dot_files': [],
                'png_output_dir': png_dir,
                'error': 'lua_bytes is empty'
            }

        if not closure_paths or len(closure_paths) == 0:
            return {
                'success': False,
                'dot_files': [],
                'png_output_dir': png_dir,
                'error': 'closure_paths is empty'
            }

        chunk = parse_bytes(lua_bytes)
        results = []

        for closure_path in closure_paths:
            closure_id = _get_linear_id(closure_path, chunk)

            # 构建 CFG
            cfg = build_cfg_for_closure(chunk, closure_path)

            if cfg is None:
                return {
                    'success': False,
                    'dot_files': results,
                    'png_output_dir': png_dir,
                    'error': f'Failed to build CFG for {closure_path}'
                }

            # 生成 DOT 内容
            dot_content = cfg.to_dot(include_instructions=True)

            # 保存 DOT 文件到本地
            dot_filename = f"{base_name}.{closure_id}.dot"
            dot_path = os.path.join(dot_dir, dot_filename)
            cfg.save_dot(dot_path, include_instructions=True)

            results.append({
                'closure_id': closure_id,
                'closure_path': closure_path,
                'dot_content': dot_content,
                'dot_path': dot_path,
                'png_filename': f"{base_name}.{closure_id}.png"
            })

        return {
            'success': True,
            'dot_files': results,
            'png_output_dir': png_dir,
            'error': None
        }

    except Exception as e:
        import traceback
        return {
            'success': False,
            'dot_files': [],
            'png_output_dir': png_dir,
            'error': str(e),
            'traceback': traceback.format_exc()
        }


def _get_linear_id(closure_path: str, chunk) -> str:
    """
    将闭包路径转换为线性 ID (F0, F1, F2...)

    Args:
        closure_path: 闭包路径 (如 "main", "F0", "F0/1")
        chunk: 解析后的 LuaChunk

    Returns:
        线性 ID (如 "main", "F0", "F1")
    """
    if closure_path == "main":
        return "main"

    # Convert path like "F0" or "F0/1" to linear ID
    # First, get all closures in order and find the matching one
    closures = _list_closures(chunk.main)

    for closure in closures:
        if closure['path'] == closure_path:
            return closure['id']

    # Fallback: use the path itself as ID
    return closure_path.replace("/", "_")
