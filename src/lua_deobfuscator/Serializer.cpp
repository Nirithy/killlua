#include "Serializer.h"

namespace lua_deobfuscator {

Serializer::Serializer(const LuaChunk& chunk) : chunk(chunk) {}

std::vector<uint8_t> Serializer::serialize(const LuaChunk& chunk) {
    Serializer s(chunk);
    return s.do_serialize();
}

std::vector<uint8_t> Serializer::do_serialize() {
    serialize_header(chunk.header);
    serialize_prototype(chunk.main, chunk.header);
    return writer.get_data();
}

void Serializer::serialize_header(const LuaHeader& h) {
    writer.write_bytes(h.signature);
    writer.write_byte(h.version);
    writer.write_byte(h.format);
    writer.write_byte(h.endianness);
    writer.set_endian(h.endianness == 1);
    writer.write_byte(h.size_int);
    writer.write_byte(h.size_size_t);
    writer.write_byte(h.size_instruction);
    writer.write_byte(h.size_lua_number);
    writer.write_byte(h.integral_flag);
    writer.write_bytes(h.tail);
}

void Serializer::write_lua_string(const std::string& s, size_t size_t_size) {
    if (s.empty()) {
        writer.write_uint64(0, size_t_size);
    } else {
        writer.write_uint64(s.length() + 1, size_t_size);
        std::vector<uint8_t> bytes(s.begin(), s.end());
        writer.write_bytes(bytes);
        writer.write_byte(0);
    }
}

void Serializer::serialize_prototype(std::shared_ptr<Prototype> p, const LuaHeader& h) {
    writer.write_int32(p->line_defined, h.size_int);
    writer.write_int32(p->last_line_defined, h.size_int);
    writer.write_byte(p->num_params);
    writer.write_byte(p->is_vararg);
    writer.write_byte(p->max_stack_size);

    // Code
    writer.write_uint32(p->code.size(), h.size_int);
    for (const auto& instr : p->code) {
        writer.write_uint32(instr.raw, 4);
    }

    // Constants
    writer.write_uint32(p->constants.size(), h.size_int);
    for (const auto& c : p->constants) {
        writer.write_byte(static_cast<uint8_t>(c.type));
        switch (c.type) {
            case LuaConstantType::NIL: break;
            case LuaConstantType::BOOLEAN: writer.write_byte(std::get<bool>(c.value) ? 1 : 0); break;
            case LuaConstantType::NUMBER: writer.write_double(std::get<double>(c.value), h.size_lua_number); break;
            case LuaConstantType::STRING: write_lua_string(std::get<std::string>(c.value), h.size_size_t); break;
            case LuaConstantType::BIGNUMBER: write_lua_string(std::get<std::string>(c.value), h.size_size_t); break;
            case LuaConstantType::INT: writer.write_int32(static_cast<int32_t>(std::get<int64_t>(c.value)), 4); break;
        }
    }

    // Protos
    writer.write_uint32(p->protos.size(), h.size_int);
    for (const auto& child : p->protos) {
        serialize_prototype(child, h);
    }

    // Upvalues
    writer.write_uint32(p->upvalues.size(), h.size_int);
    for (const auto& u : p->upvalues) {
        writer.write_byte(u.instack ? 1 : 0);
        writer.write_byte(u.idx);
    }

    // Debug info
    write_lua_string(p->source, h.size_size_t);

    writer.write_uint32(p->lineinfo.size(), h.size_int);
    for (int line : p->lineinfo) {
        writer.write_int32(line, 4);
    }

    writer.write_uint32(p->locvars.size(), h.size_int);
    for (const auto& lv : p->locvars) {
        write_lua_string(lv.varname, h.size_size_t);
        writer.write_int32(lv.startpc, 4);
        writer.write_int32(lv.endpc, 4);
    }

    // Upvalue names count (only those that are not None/empty in Python)
    uint32_t named_upvals = 0;
    for (const auto& u : p->upvalues) {
        if (!u.name.empty()) named_upvals++;
        else break;
    }
    writer.write_uint32(named_upvals, h.size_int);
    for (uint32_t i = 0; i < named_upvals; ++i) {
        write_lua_string(p->upvalues[i].name, h.size_size_t);
    }
}

} // namespace lua_deobfuscator
