#ifndef LUA_DEOBFUSCATOR_H
#define LUA_DEOBFUSCATOR_H

#include "LuaTypes.h"
#include "CFG.h"
#include <vector>
#include <string>

namespace lua_deobfuscator {

struct DeobfuscationResult {
    bool success;
    std::string pass_name;
    int changes_made;
    std::string details;
};

class Deobfuscator {
public:
    Deobfuscator(std::shared_ptr<Prototype> proto);

    DeobfuscationResult run_constant_folding();
    DeobfuscationResult run_dead_code_elimination();
    DeobfuscationResult run_dead_branch_elimination();
    DeobfuscationResult run_sequential_block_merging();

    std::vector<DeobfuscationResult> run_all_passes(int max_iterations = 10);

private:
    std::shared_ptr<Prototype> proto;
    std::unique_ptr<CFG> cfg;

    void rebuild_from_cfg();
    int simplify_jmp_chains();
    int find_jmp_chain_target(int block_id, std::set<int>& visited);
    bool is_jmp_only_block(int block_id);
};

} // namespace lua_deobfuscator

#endif // LUA_DEOBFUSCATOR_H
