#ifndef LUA_TYPES_H
#define LUA_TYPES_H

#include <string>
#include <vector>
#include <variant>
#include <cstdint>
#include <memory>
#include "Opcodes.h"

namespace lua_deobfuscator {

enum class LuaFormat {
    LUAJ_HYBRID = 1,
    LUA53_OFFICIAL = 2
};

struct LuaHeader {
    std::vector<uint8_t> signature;
    uint8_t version;
    uint8_t format;
    uint8_t endianness;
    uint8_t size_int;
    uint8_t size_size_t;
    uint8_t size_instruction;
    uint8_t size_lua_number;
    uint8_t integral_flag;
    std::vector<uint8_t> tail;
};

struct Instruction {
    uint32_t raw;
    int opcode;
    std::string opcode_name;
    int a, b, c, bx, sbx, ax;
    OpMode mode;

    static Instruction decode(uint32_t raw) {
        Instruction instr;
        instr.raw = raw;
        instr.opcode = raw & 0x3F;
        instr.a = (raw >> 6) & 0xFF;
        instr.c = (raw >> 14) & 0x1FF;
        instr.b = (raw >> 23) & 0x1FF;
        instr.bx = (raw >> 14) & 0x3FFFF;
        instr.sbx = instr.bx - 131071;
        instr.ax = (raw >> 6) & 0x3FFFFFF;

        instr.mode = get_opcode_mode(instr.opcode);
        instr.opcode_name = get_opcode_name(instr.opcode);
        return instr;
    }

    static Instruction encode_new(int opcode, int a = 0, int b = 0, int c = 0, int sbx = 0, int ax = 0) {
        OpMode mode = get_opcode_mode(opcode);
        uint32_t raw = 0;
        int bx = 0;

        if (mode == OpMode::iABC) {
            raw = (opcode & 0x3F) | ((a & 0xFF) << 6) | ((c & 0x1FF) << 14) | ((b & 0x1FF) << 23);
        } else if (mode == OpMode::iABx || mode == OpMode::iAsBx) {
            bx = sbx + 131071;
            raw = (opcode & 0x3F) | ((a & 0xFF) << 6) | ((bx & 0x3FFFF) << 14);
        } else { // iAx
            raw = (opcode & 0x3F) | ((ax & 0x3FFFFFF) << 6);
        }
        return decode(raw);
    }
};

enum class LuaConstantType {
    NIL = 0,
    BOOLEAN = 1,
    BIGNUMBER = 2,
    NUMBER = 3,
    STRING = 4,
    INT = 0xFE
};

struct LuaConstant {
    LuaConstantType type;
    std::variant<std::monostate, bool, double, int64_t, std::string> value;

    std::string to_string() const {
        switch (type) {
            case LuaConstantType::NIL: return "nil";
            case LuaConstantType::BOOLEAN: return std::get<bool>(value) ? "true" : "false";
            case LuaConstantType::STRING: return "\"" + std::get<std::string>(value) + "\"";
            case LuaConstantType::NUMBER: return std::to_string(std::get<double>(value));
            case LuaConstantType::INT: return std::to_string(std::get<int64_t>(value));
            case LuaConstantType::BIGNUMBER: return std::get<std::string>(value);
            default: return "unknown";
        }
    }
};

struct LocVar {
    std::string varname;
    int startpc;
    int endpc;
};

struct Upvalue {
    std::string name;
    bool instack;
    int idx;
};

struct Prototype {
    std::string source;
    int line_defined;
    int last_line_defined;
    int num_params;
    int is_vararg;
    int max_stack_size;
    std::vector<Instruction> code;
    std::vector<LuaConstant> constants;
    std::vector<std::shared_ptr<Prototype>> protos;
    std::vector<Upvalue> upvalues;
    std::vector<int> lineinfo;
    std::vector<LocVar> locvars;
};

struct LuaChunk {
    LuaHeader header;
    std::shared_ptr<Prototype> main;
};

} // namespace lua_deobfuscator

#endif // LUA_TYPES_H
