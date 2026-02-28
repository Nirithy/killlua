#ifndef LUA_SERIALIZER_H
#define LUA_SERIALIZER_H

#include "LuaTypes.h"
#include "ByteUtils.h"

namespace lua_deobfuscator {

class Serializer {
public:
    static std::vector<uint8_t> serialize(const LuaChunk& chunk);

private:
    Serializer(const LuaChunk& chunk);
    std::vector<uint8_t> do_serialize();

    void serialize_header(const LuaHeader& header);
    void serialize_prototype(std::shared_ptr<Prototype> proto, const LuaHeader& header);

    void write_lua_string(const std::string& s, size_t size_t_size);

    const LuaChunk& chunk;
    ByteWriter writer;
};

} // namespace lua_deobfuscator

#endif // LUA_SERIALIZER_H
