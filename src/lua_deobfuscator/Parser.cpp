#include "Parser.h"
#include <stdexcept>
#include <algorithm>

namespace lua_deobfuscator {

Parser::Parser(const std::vector<uint8_t>& data) : reader(data) {}

LuaChunk Parser::parse(const std::vector<uint8_t>& data) {
    Parser p(data);
    return p.do_parse();
}

LuaChunk Parser::do_parse() {
    auto sig = reader.read_bytes(4);
    if (sig != std::vector<uint8_t>{0x1B, 'L', 'u', 'a'}) {
        throw std::runtime_error("Invalid Lua signature");
    }

    uint8_t version = reader.read_byte();
    reader.seek(0); // Back to start for full header parse

    LuaChunk chunk;
    if (version == 0x52) {
        chunk.header = parse_header_52();
        chunk.main = parse_prototype_52(chunk.header);
    } else if (version == 0x53) {
        chunk.header = parse_header_53();
        reader.read_byte(); // num_upvalues
        chunk.main = parse_prototype_53(chunk.header);
    } else {
        throw std::runtime_error("Unsupported Lua version: 0x" + std::to_string(version));
    }
    return chunk;
}

LuaHeader Parser::parse_header_52() {
    LuaHeader h;
    h.signature = reader.read_bytes(4);
    h.version = reader.read_byte();
    h.format = reader.read_byte();
    h.endianness = reader.read_byte();
    reader.set_endian(h.endianness == 1);
    h.size_int = reader.read_byte();
    h.size_size_t = reader.read_byte();
    h.size_instruction = reader.read_byte();
    h.size_lua_number = reader.read_byte();
    h.integral_flag = reader.read_byte();
    h.tail = reader.read_bytes(6);
    return h;
}

LuaHeader Parser::parse_header_53() {
    LuaHeader h;
    h.signature = reader.read_bytes(4);
    h.version = reader.read_byte();
    h.format = reader.read_byte();
    h.tail = reader.read_bytes(6); // LUAC_DATA
    h.size_int = reader.read_byte();
    h.size_size_t = reader.read_byte();
    h.size_instruction = reader.read_byte();
    uint8_t size_lua_integer = reader.read_byte();
    h.size_lua_number = reader.read_byte();

    // Check endianness via LUAC_INT (0x5678)
    int64_t luac_int = reader.read_int64(size_lua_integer);
    if (luac_int != 0x5678) {
        // Try big endian? Standard is 0x5678 in native endian.
    }
    reader.set_endian(true);
    h.endianness = 1;

    reader.read_double(h.size_lua_number); // LUAC_NUM (370.5)

    // Convert to 5.2-style internal header for compatibility
    h.version = 0x52;
    h.size_size_t = 4; // Use 4 for hybrid compatibility
    return h;
}

std::string Parser::read_lua_string(size_t size_t_size) {
    uint64_t size = reader.read_uint64(size_t_size);
    if (size == 0) return "";
    auto bytes = reader.read_bytes(size);
    if (bytes.empty()) return "";
    return std::string(reinterpret_cast<char*>(bytes.data()), size - 1);
}

std::string Parser::read_lua_string_53() {
    uint8_t size_byte = reader.read_byte();
    uint64_t size;
    if (size_byte == 0) return "";
    if (size_byte == 0xFF) {
        size = reader.read_uint64(8); // size_t is usually 8 in 5.3
    } else {
        size = size_byte;
    }
    if (size <= 1) return "";
    auto bytes = reader.read_bytes(size - 1);
    return std::string(reinterpret_cast<char*>(bytes.data()), size - 1);
}

std::shared_ptr<Prototype> Parser::parse_prototype_52(const LuaHeader& header) {
    auto p = std::make_shared<Prototype>();
    p->line_defined = reader.read_int32(header.size_int);
    p->last_line_defined = reader.read_int32(header.size_int);
    p->num_params = reader.read_byte();
    p->is_vararg = reader.read_byte();
    p->max_stack_size = reader.read_byte();

    // Code
    uint32_t code_size = reader.read_uint32(header.size_int);
    for (uint32_t i = 0; i < code_size; ++i) {
        p->code.push_back(Instruction::decode(reader.read_uint32(4)));
    }

    // Constants
    uint32_t const_size = reader.read_uint32(header.size_int);
    for (uint32_t i = 0; i < const_size; ++i) {
        LuaConstant c;
        uint8_t type = reader.read_byte();
        c.type = static_cast<LuaConstantType>(type);
        switch (c.type) {
            case LuaConstantType::NIL: c.value = std::monostate{}; break;
            case LuaConstantType::BOOLEAN: c.value = (reader.read_byte() != 0); break;
            case LuaConstantType::NUMBER: c.value = reader.read_double(header.size_lua_number); break;
            case LuaConstantType::STRING: c.value = read_lua_string(header.size_size_t); break;
            case LuaConstantType::BIGNUMBER: c.value = read_lua_string(header.size_size_t); break;
            case LuaConstantType::INT: c.value = static_cast<int64_t>(reader.read_int32(4)); break;
            default: throw std::runtime_error("Unknown constant type: " + std::to_string(type));
        }
        p->constants.push_back(c);
    }

    // Protos
    uint32_t proto_size = reader.read_uint32(header.size_int);
    for (uint32_t i = 0; i < proto_size; ++i) {
        p->protos.push_back(parse_prototype_52(header));
    }

    // Upvalues
    uint32_t upval_size = reader.read_uint32(header.size_int);
    for (uint32_t i = 0; i < upval_size; ++i) {
        Upvalue u;
        u.instack = (reader.read_byte() != 0);
        u.idx = reader.read_byte();
        p->upvalues.push_back(u);
    }

    // Debug info
    p->source = read_lua_string(header.size_size_t);

    uint32_t lineinfo_size = reader.read_uint32(header.size_int);
    for (uint32_t i = 0; i < lineinfo_size; ++i) {
        p->lineinfo.push_back(reader.read_int32(4));
    }

    uint32_t locvar_size = reader.read_uint32(header.size_int);
    for (uint32_t i = 0; i < locvar_size; ++i) {
        LocVar lv;
        lv.varname = read_lua_string(header.size_size_t);
        lv.startpc = reader.read_int32(4);
        lv.endpc = reader.read_int32(4);
        p->locvars.push_back(lv);
    }

    uint32_t upval_name_size = reader.read_uint32(header.size_int);
    for (uint32_t i = 0; i < upval_name_size; ++i) {
        std::string name = read_lua_string(header.size_size_t);
        if (i < p->upvalues.size()) p->upvalues[i].name = name;
    }

    return p;
}

std::shared_ptr<Prototype> Parser::parse_prototype_53(const LuaHeader& header, const std::string& parent_source) {
    auto p = std::make_shared<Prototype>();
    p->source = read_lua_string_53();
    if (p->source.empty()) p->source = parent_source;

    p->line_defined = reader.read_int32(4);
    p->last_line_defined = reader.read_int32(4);
    p->num_params = reader.read_byte();
    p->is_vararg = reader.read_byte();
    p->max_stack_size = reader.read_byte();

    // Code
    uint32_t code_size = reader.read_uint32(4);
    for (uint32_t i = 0; i < code_size; ++i) {
        p->code.push_back(Instruction::decode(reader.read_uint32(4)));
    }

    // Constants
    uint32_t const_size = reader.read_uint32(4);
    for (uint32_t i = 0; i < const_size; ++i) {
        LuaConstant c;
        uint8_t type = reader.read_byte();
        if (type == 0) { c.type = LuaConstantType::NIL; c.value = std::monostate{}; }
        else if (type == 1) { c.type = LuaConstantType::BOOLEAN; c.value = (reader.read_byte() != 0); }
        else if (type == 3) { c.type = LuaConstantType::NUMBER; c.value = reader.read_double(8); }
        else if (type == 0x13) { c.type = LuaConstantType::INT; c.value = reader.read_int64(8); }
        else if (type == 4 || type == 0x14) { c.type = LuaConstantType::STRING; c.value = read_lua_string_53(); }
        p->constants.push_back(c);
    }

    // Upvalues
    uint32_t upval_size = reader.read_uint32(4);
    for (uint32_t i = 0; i < upval_size; ++i) {
        Upvalue u;
        u.instack = (reader.read_byte() != 0);
        u.idx = reader.read_byte();
        p->upvalues.push_back(u);
    }

    // Protos
    uint32_t proto_size = reader.read_uint32(4);
    for (uint32_t i = 0; i < proto_size; ++i) {
        p->protos.push_back(parse_prototype_53(header, p->source));
    }

    // Debug
    uint32_t lineinfo_size = reader.read_uint32(4);
    for (uint32_t i = 0; i < lineinfo_size; ++i) {
        p->lineinfo.push_back(reader.read_int32(4));
    }

    uint32_t locvar_size = reader.read_uint32(4);
    for (uint32_t i = 0; i < locvar_size; ++i) {
        LocVar lv;
        lv.varname = read_lua_string_53();
        lv.startpc = reader.read_int32(4);
        lv.endpc = reader.read_int32(4);
        p->locvars.push_back(lv);
    }

    uint32_t upval_name_size = reader.read_uint32(4);
    for (uint32_t i = 0; i < upval_name_size; ++i) {
        std::string name = read_lua_string_53();
        if (i < p->upvalues.size()) p->upvalues[i].name = name;
    }

    return p;
}

} // namespace lua_deobfuscator
