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
    struct RegValue {
        enum { UNKNOWN, CONSTANT, MULTIPLE } state = UNKNOWN;
        LuaConstant val;

        bool operator==(const RegValue& other) const {
            if (state != other.state) return false;
            if (state != CONSTANT) return true;
            if (val.type != other.val.type) return false;
            return val.value == other.val.value;
        }
        bool operator!=(const RegValue& other) const { return !(*this == other); }
    };

    Deobfuscator(std::shared_ptr<Prototype> proto);

    DeobfuscationResult run_constant_folding();
    DeobfuscationResult run_constant_propagation();
    DeobfuscationResult run_dead_code_elimination();
    DeobfuscationResult run_dead_branch_elimination();
    DeobfuscationResult run_sequential_block_merging();
    DeobfuscationResult run_control_flow_deflattening();
    DeobfuscationResult run_redundant_store_elimination();
    DeobfuscationResult run_conditional_branch_normalization();

    std::vector<DeobfuscationResult> run_all_passes(int max_iterations = 10);

private:
    std::shared_ptr<Prototype> proto;
    std::unique_ptr<CFG> cfg;

    std::map<int, std::vector<RegValue>> block_entry_regs;
    std::map<int, std::vector<RegValue>> block_exit_regs;

    void perform_constant_propagation();
    void rebuild_from_cfg();
    int simplify_jmp_chains();
    int find_jmp_chain_target(int block_id, std::set<int>& visited);
    bool is_jmp_only_block(int block_id);
};

} // namespace lua_deobfuscator

#endif // LUA_DEOBFUSCATOR_H
