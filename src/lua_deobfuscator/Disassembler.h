#ifndef LUA_DISASSEMBLER_H
#define LUA_DISASSEMBLER_H

#include "LuaTypes.h"
#include <string>
#include <vector>
#include <set>
#include <sstream>

namespace lua_deobfuscator {

class Disassembler {
public:
    Disassembler(const LuaChunk& chunk);
    std::string disassemble(const std::string& closure_filter = "", bool include_children = true);

public:
    static std::string format_instruction(const Instruction& instr, std::shared_ptr<Prototype> proto, int pc, int closure_offset, const std::set<int>& jump_targets);
    static std::string format_constant(const LuaConstant& c);
    static std::set<int> collect_jump_targets(std::shared_ptr<Prototype> proto);

private:
    void disassemble_prototype(std::shared_ptr<Prototype> proto, int func_num, bool include_children, const std::string& parent_source = "");

    void emit(const std::string& line = "");

    const LuaChunk& chunk;
    std::stringstream output;
    int indent_level;
    int func_counter;
};

} // namespace lua_deobfuscator

#endif // LUA_DISASSEMBLER_H
