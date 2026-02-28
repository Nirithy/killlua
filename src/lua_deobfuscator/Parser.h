#ifndef LUA_PARSER_H
#define LUA_PARSER_H

#include "LuaTypes.h"
#include "ByteUtils.h"
#include <memory>

namespace lua_deobfuscator {

class Parser {
public:
    static LuaChunk parse(const std::vector<uint8_t>& data);

private:
    Parser(const std::vector<uint8_t>& data);
    LuaChunk do_parse();

    LuaHeader parse_header_52();
    LuaHeader parse_header_53();
    std::shared_ptr<Prototype> parse_prototype_52(const LuaHeader& header);
    std::shared_ptr<Prototype> parse_prototype_53(const LuaHeader& header, const std::string& parent_source = "");

    std::string read_lua_string(size_t size_t_size);
    std::string read_lua_string_53();

    ByteReader reader;
};

} // namespace lua_deobfuscator

#endif // LUA_PARSER_H
