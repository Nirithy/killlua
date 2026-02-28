#ifndef LUA_CFG_H
#define LUA_CFG_H

#include "LuaTypes.h"
#include <vector>
#include <set>
#include <map>
#include <memory>

namespace lua_deobfuscator {

enum class EdgeType {
    SEQUENTIAL,
    JUMP,
    COND_TRUE,
    COND_FALSE,
    LOOP_BACK,
    LOOP_EXIT,
    RETURN
};

struct BasicBlock {
    int id;
    int start_pc;
    int end_pc; // Exclusive
    std::vector<Instruction> instructions;
    bool is_entry = false;
    bool is_exit = false;
    std::set<int> predecessors;
    std::set<int> successors;

    int size() const { return end_pc - start_pc; }
};

class CFG {
public:
    CFG(std::shared_ptr<Prototype> proto);

    std::map<int, std::shared_ptr<BasicBlock>> blocks;
    std::map<int, int> pc_to_block;
    std::map<std::pair<int, int>, EdgeType> edges;

    std::string to_dot(bool include_instructions = true);
    std::set<int> find_unreachable_blocks();
    void remove_block(int block_id);
    std::vector<Instruction> rebuild_code();

private:
    void build();
    std::set<int> find_leaders();
    void create_blocks(const std::set<int>& leaders);
    void create_edges();
    void mark_special_blocks();
    void add_edge(int from_id, int to_pc, EdgeType type);

    std::shared_ptr<Prototype> proto;
    int block_counter;
};

} // namespace lua_deobfuscator

#endif // LUA_CFG_H
