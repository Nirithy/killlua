#include "Deobfuscator.h"
#include <cmath>
#include <algorithm>

namespace lua_deobfuscator {

Deobfuscator::Deobfuscator(std::shared_ptr<Prototype> proto) : proto(proto) {}

DeobfuscationResult Deobfuscator::run_constant_folding() {
    int changes = 0;
    for (size_t i = 0; i < proto->code.size(); ++i) {
        auto& instr = proto->code[i];
        Opcode op = static_cast<Opcode>(instr.opcode);

        if (op == Opcode::ADD || op == Opcode::SUB || op == Opcode::MUL || op == Opcode::DIV ||
            op == Opcode::MOD || op == Opcode::IDIV || op == Opcode::BAND || op == Opcode::BOR ||
            op == Opcode::BXOR || op == Opcode::SHL || op == Opcode::SHR || op == Opcode::POW) {

            if (ISK(instr.b) && ISK(instr.c)) {
                int b_idx = INDEXK(instr.b);
                int c_idx = INDEXK(instr.c);

                if (b_idx < (int)proto->constants.size() && c_idx < (int)proto->constants.size()) {
                    auto const& kb = proto->constants[b_idx];
                    auto const& kc = proto->constants[c_idx];

                    if ((kb.type == LuaConstantType::NUMBER || kb.type == LuaConstantType::INT) &&
                        (kc.type == LuaConstantType::NUMBER || kc.type == LuaConstantType::INT)) {

                        double vb = (kb.type == LuaConstantType::INT) ? static_cast<double>(std::get<int64_t>(kb.value)) : std::get<double>(kb.value);
                        double vc = (kc.type == LuaConstantType::INT) ? static_cast<double>(std::get<int64_t>(kc.value)) : std::get<double>(kc.value);
                        double res = 0;
                        bool valid = true;

                        if (op == Opcode::ADD) res = vb + vc;
                        else if (op == Opcode::SUB) res = vb - vc;
                        else if (op == Opcode::MUL) res = vb * vc;
                        else if (op == Opcode::DIV) { if (vc != 0) res = vb / vc; else valid = false; }
                        else if (op == Opcode::MOD) { if (vc != 0) res = std::fmod(vb, vc); else valid = false; }
                        else if (op == Opcode::POW) res = std::pow(vb, vc);
                        else valid = false; // Int-only ops omitted for brevity

                        if (valid) {
                            // Replacement with LOADK
                            LuaConstant nc;
                            nc.type = LuaConstantType::NUMBER;
                            nc.value = res;
                            int n_idx = proto->constants.size();
                            proto->constants.push_back(nc);
                            instr = Instruction::encode_new(static_cast<int>(Opcode::LOADK), instr.a, 0, 0, 0, 0);
                            instr.bx = n_idx;
                            instr.raw = ((instr.opcode & 0x3F) | ((instr.a & 0xFF) << 6) | ((instr.bx & 0x3FFFF) << 14));
                            changes++;
                        }
                    }
                }
            }
        }
    }
    return {changes > 0, "Constant Folding", changes, "Folded " + std::to_string(changes) + " expressions"};
}

DeobfuscationResult Deobfuscator::run_dead_code_elimination() {
    if (!cfg) cfg = std::make_unique<CFG>(proto);
    auto unreachable = cfg->find_unreachable_blocks();

    // Original Python preserves trailing RETURN blocks
    int max_end_pc = 0;
    for (auto const& [id, block] : cfg->blocks) max_end_pc = std::max(max_end_pc, block->end_pc);

    std::set<int> trailing_returns;
    for (auto const& [id, block] : cfg->blocks) {
        if (block->end_pc == max_end_pc && !block->instructions.empty() && static_cast<Opcode>(block->instructions.back().opcode) == Opcode::RETURN) {
            trailing_returns.insert(id);
        }
    }

    int changes = 0;
    for (int id : unreachable) {
        if (!trailing_returns.count(id)) {
            cfg->remove_block(id);
            changes++;
        }
    }

    if (changes > 0) rebuild_from_cfg();

    return {true, "Dead Code Elimination", changes, "Removed " + std::to_string(changes) + " unreachable blocks"};
}

void Deobfuscator::rebuild_from_cfg() {
    proto->code = cfg->rebuild_code();
    cfg.reset();
}
DeobfuscationResult Deobfuscator::run_dead_branch_elimination() {
    if (!cfg) cfg = std::make_unique<CFG>(proto);

    // 1. Find garbage blocks
    std::set<int> garbage;
    int max_end_pc = 0;
    for (auto const& [id, block] : cfg->blocks) max_end_pc = std::max(max_end_pc, block->end_pc);

    // Dead ends
    for (auto const& [id, block] : cfg->blocks) {
        if (block->successors.empty() && !block->instructions.empty()) {
            Opcode op = static_cast<Opcode>(block->instructions.back().opcode);
            if (op != Opcode::RETURN && op != Opcode::TAILCALL) garbage.insert(id);
        }
    }

    // Unreachable
    auto unreachable = cfg->find_unreachable_blocks();
    for (int id : unreachable) {
        // preserve trailing returns
        bool is_trailing = (cfg->blocks[id]->end_pc == max_end_pc && !cfg->blocks[id]->instructions.empty() && static_cast<Opcode>(cfg->blocks[id]->instructions.back().opcode) == Opcode::RETURN);
        if (!is_trailing) garbage.insert(id);
    }

    int changes = 0;
    std::set<Opcode> conditional_ops = {Opcode::EQ, Opcode::LT, Opcode::LE, Opcode::NEQ, Opcode::GE, Opcode::GT, Opcode::TEST, Opcode::TESTSET, Opcode::FORLOOP, Opcode::TFORLOOP};

    for (auto const& [id, block] : cfg->blocks) {
        if (garbage.count(id)) continue;
        if (block->instructions.empty()) continue;
        auto& last_instr = block->instructions.back();
        if (conditional_ops.count(static_cast<Opcode>(last_instr.opcode))) {
            std::vector<int> succs(block->successors.begin(), block->successors.end());
            if (succs.size() == 2) {
                int s1 = succs[0], s2 = succs[1];
                bool g1 = garbage.count(s1), g2 = garbage.count(s2);
                if ((g1 && !g2) || (!g1 && g2)) {
                    int valid_succ = g1 ? s2 : s1;
                    int garbage_succ = g1 ? s1 : s2;

                    // Expansion logic (simplified)
                    Opcode op = static_cast<Opcode>(last_instr.opcode);
                    if (op == Opcode::TESTSET) {
                        // if garbage is COND_FALSE (next instr), then MOVE
                        EdgeType et = cfg->edges[{id, valid_succ}];
                        if (et == EdgeType::COND_FALSE) {
                            last_instr = Instruction::encode_new(static_cast<int>(Opcode::MOVE), last_instr.a, last_instr.b);
                        } else {
                            block->instructions.pop_back();
                        }
                    } else if (op == Opcode::TEST || op == Opcode::EQ || op == Opcode::LT || op == Opcode::LE || op == Opcode::NEQ || op == Opcode::GE || op == Opcode::GT) {
                        block->instructions.pop_back();
                    }
                    // FORLOOP/TFORLOOP expansion is omitted for brevity

                    // Update CFG
                    block->successors.erase(garbage_succ);
                    cfg->blocks[garbage_succ]->predecessors.erase(id);
                    cfg->edges.erase({id, garbage_succ});
                    cfg->edges[{id, valid_succ}] = EdgeType::SEQUENTIAL;

                    changes++;
                }
            }
        }
    }

    if (changes > 0) rebuild_from_cfg();
    return {true, "Dead Branch Elimination", changes, "Eliminated " + std::to_string(changes) + " dead branch(es)"};
}
DeobfuscationResult Deobfuscator::run_sequential_block_merging() {
    if (!cfg) cfg = std::make_unique<CFG>(proto);
    int changes = 0;
    bool changed = true;
    while (changed) {
        changed = false;
        std::vector<int> ids;
        for (auto const& [id, block] : cfg->blocks) ids.push_back(id);
        std::sort(ids.begin(), ids.end());

        for (int a_id : ids) {
            if (!cfg->blocks.count(a_id)) continue;
            auto block_a = cfg->blocks[a_id];
            if (block_a->successors.size() == 1) {
                int b_id = *block_a->successors.begin();
                auto block_b = cfg->blocks[b_id];
                if (block_b->predecessors.size() == 1 && !block_b->is_entry) {
                    // Merge A and B
                    if (!block_a->instructions.empty()) {
                        Opcode op = static_cast<Opcode>(block_a->instructions.back().opcode);
                        if (op == Opcode::JMP) block_a->instructions.pop_back();
                        else if (op == Opcode::LOADBOOL && block_a->instructions.back().c != 0) {
                            block_a->instructions.back().c = 0;
                            block_a->instructions.back().raw = Instruction::encode_new(static_cast<int>(Opcode::LOADBOOL), block_a->instructions.back().a, block_a->instructions.back().b, 0).raw;
                        } else if (op == Opcode::FORPREP) {
                            int a = block_a->instructions.back().a;
                            block_a->instructions.back() = Instruction::encode_new(static_cast<int>(Opcode::SUB), a, a, a + 2);
                        } else if (op == Opcode::RETURN || op == Opcode::TAILCALL || op == Opcode::FORLOOP || op == Opcode::TFORLOOP ||
                                   op == Opcode::EQ || op == Opcode::LT || op == Opcode::LE || op == Opcode::NEQ || op == Opcode::GE || op == Opcode::GT ||
                                   op == Opcode::TEST || op == Opcode::TESTSET) {
                            continue; // Not mergeable
                        }
                    }

                    for (const auto& instr : block_b->instructions) block_a->instructions.push_back(instr);
                    block_a->end_pc = block_b->end_pc;
                    block_a->successors = block_b->successors;
                    for (int succ_id : block_b->successors) {
                        cfg->blocks[succ_id]->predecessors.erase(b_id);
                        cfg->blocks[succ_id]->predecessors.insert(a_id);
                        cfg->edges[{a_id, succ_id}] = cfg->edges[{b_id, succ_id}];
                    }
                    if (block_b->is_exit) block_a->is_exit = true;

                    cfg->remove_block(b_id);
                    changes++;
                    changed = true;
                    break;
                }
            }
        }
    }

    if (changes > 0) rebuild_from_cfg();
    return {true, "Sequential Block Merging", changes, "Merged " + std::to_string(changes) + " block pair(s)"};
}

} // namespace lua_deobfuscator
