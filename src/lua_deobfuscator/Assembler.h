#ifndef LUA_ASSEMBLER_H
#define LUA_ASSEMBLER_H

#include "LuaTypes.h"
#include <string>
#include <vector>
#include <memory>

namespace lua_deobfuscator {

class Assembler {
public:
    static LuaChunk assemble(const std::string& lasm);

private:
    Assembler(const std::string& lasm);
    LuaChunk do_assemble();

    struct Token {
        enum Type {
            DIRECTIVE, // .func, .source, etc.
            LABEL,     // :goto_0
            INSTRUCTION, // MOVE, LOADK, etc.
            REGISTER,  // v0, v1
            UPVAL,     // u0, u1
            CONSTANT,  // "string", 123, true, nil, K0
            IDENTIFIER,
            NUMBER,
            STRING,
            COMMENT,
            NEWLINE,
            END_OF_FILE
        } type;
        std::string value;
        int line;
    };

    std::vector<Token> tokenize();
    std::shared_ptr<Prototype> parse_prototype(std::vector<Token>::iterator& it, const std::vector<Token>::iterator& end);

    std::string lasm;
};

} // namespace lua_deobfuscator

#endif // LUA_ASSEMBLER_H
