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
                        else if (op == Opcode::IDIV) { if (vc != 0) res = std::floor(vb / vc); else valid = false; }
                        else if (op == Opcode::BAND) res = static_cast<double>(static_cast<int64_t>(vb) & static_cast<int64_t>(vc));
                        else if (op == Opcode::BOR) res = static_cast<double>(static_cast<int64_t>(vb) | static_cast<int64_t>(vc));
                        else if (op == Opcode::BXOR) res = static_cast<double>(static_cast<int64_t>(vb) ^ static_cast<int64_t>(vc));
                        else if (op == Opcode::SHL) res = static_cast<double>(static_cast<int64_t>(vb) << static_cast<int64_t>(vc));
                        else if (op == Opcode::SHR) res = static_cast<double>(static_cast<int64_t>(vb) >> static_cast<int64_t>(vc));
                        else valid = false;

                        if (valid) {
                            // Replacement with LOADK
                            LuaConstant nc;
                            nc.type = LuaConstantType::NUMBER;
                            nc.value = res;
                            int n_idx = proto->constants.size();
                            proto->constants.push_back(nc);
                            instr = Instruction::encode_new(static_cast<int>(Opcode::LOADK), proto->version, instr.a, 0, 0, 0, 0);
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

void Deobfuscator::perform_constant_propagation() {
    if (!cfg) cfg = std::make_unique<CFG>(proto);

    block_entry_regs.clear();
    block_exit_regs.clear();

    for (auto const& [id, block] : cfg->blocks) {
        block_entry_regs[id].assign(256, {RegValue::UNKNOWN, {}});
        block_exit_regs[id].assign(256, {RegValue::UNKNOWN, {}});
    }

    bool changed = true;
    while (changed) {
        changed = false;
        for (auto const& [id, block] : cfg->blocks) {
            std::vector<RegValue> entry(256, {RegValue::UNKNOWN, {}});
            if (!block->is_entry) {
                bool first = true;
                for (int pred_id : block->predecessors) {
                    if (block_exit_regs[pred_id].empty()) continue;

                    const auto& pred_exit = block_exit_regs[pred_id];
                    if (first) { entry = pred_exit; first = false; }
                    else {
                        for (int i = 0; i < 256; ++i) {
                            if (entry[i].state == RegValue::MULTIPLE) continue;
                            if (entry[i].state == RegValue::UNKNOWN) {
                                entry[i] = pred_exit[i];
                            } else if (pred_exit[i].state == RegValue::UNKNOWN) {
                                // keep entry[i]
                            } else if (entry[i] != pred_exit[i]) {
                                entry[i].state = RegValue::MULTIPLE;
                            }
                        }
                    }
                }
                if (first) continue;
            }
            if (entry != block_entry_regs[id]) { block_entry_regs[id] = entry; changed = true; }

            std::vector<RegValue> current = entry;
            for (const auto& instr : block->instructions) {
                Opcode op = static_cast<Opcode>(instr.opcode);
                if (instr.a < 0 || instr.a >= 256) continue;
                if (op == Opcode::LOADK) {
                    current[instr.a].state = RegValue::CONSTANT;
                    if (instr.bx >= 0 && instr.bx < (int)proto->constants.size()) {
                        current[instr.a].val = proto->constants[instr.bx];
                    } else {
                        current[instr.a].state = RegValue::UNKNOWN;
                    }
                } else if (op == Opcode::LOADBOOL) {
                    current[instr.a].state = RegValue::CONSTANT;
                    current[instr.a].val.type = LuaConstantType::BOOLEAN;
                    current[instr.a].val.value = (instr.b != 0);
                } else if (op == Opcode::LOADNIL) {
                    for (int i = instr.a; i <= instr.a + instr.b && i < 256; ++i) {
                        current[i].state = RegValue::CONSTANT;
                        current[i].val.type = LuaConstantType::NIL;
                    }
                } else if (op == Opcode::MOVE) {
                    if (instr.b >= 0 && instr.b < 256) current[instr.a] = current[instr.b];
                } else {
                    if (op != Opcode::EQ && op != Opcode::LT && op != Opcode::LE &&
                        op != Opcode::NEQ && op != Opcode::GE && op != Opcode::GT &&
                        op != Opcode::TEST && op != Opcode::TESTSET &&
                        op != Opcode::JMP && op != Opcode::FORLOOP && op != Opcode::TFORLOOP &&
                        op != Opcode::SETTABLE && op != Opcode::SETTABUP && op != Opcode::SETUPVAL) {
                        current[instr.a].state = RegValue::MULTIPLE;
                    }
                }
            }

            if (current != block_exit_regs[id]) {
                block_exit_regs[id] = current;
                changed = true;
            }
        }
    }
}

DeobfuscationResult Deobfuscator::run_constant_propagation() {
    perform_constant_propagation();
    return {true, "Constant Propagation", 0, "Performed constant propagation"};
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

bool Deobfuscator::is_jmp_only_block(int block_id) {
    if (!cfg || !cfg->blocks.count(block_id)) return false;
    auto block = cfg->blocks[block_id];
    return block->instructions.size() == 1 && static_cast<Opcode>(block->instructions[0].opcode) == Opcode::JMP;
}

int Deobfuscator::find_jmp_chain_target(int block_id, std::set<int>& visited) {
    if (visited.count(block_id)) return -1;
    visited.insert(block_id);
    if (!is_jmp_only_block(block_id)) return block_id;
    auto block = cfg->blocks[block_id];
    if (block->successors.size() != 1) return block_id;
    return find_jmp_chain_target(*block->successors.begin(), visited);
}

int Deobfuscator::simplify_jmp_chains() {
    int changes = 0;
    std::vector<int> jmp_blocks;
    for (auto const& [id, block] : cfg->blocks) if (is_jmp_only_block(id)) jmp_blocks.push_back(id);

    for (int jmp_id : jmp_blocks) {
        std::set<int> visited;
        int final_target = find_jmp_chain_target(jmp_id, visited);
        if (final_target == -1 || final_target == jmp_id) continue;

        auto block_jmp = cfg->blocks[jmp_id];
        if (block_jmp->successors.size() != 1 || *block_jmp->successors.begin() == final_target) continue;

        std::vector<int> preds(block_jmp->predecessors.begin(), block_jmp->predecessors.end());
        for (int pred_id : preds) {
            if (is_jmp_only_block(pred_id)) continue;
            auto pred_block = cfg->blocks[pred_id];

            EdgeType et = cfg->edges[{pred_id, jmp_id}];
            cfg->edges.erase({pred_id, jmp_id});
            pred_block->successors.erase(jmp_id);
            block_jmp->predecessors.erase(pred_id);

            if (!pred_block->successors.count(final_target)) {
                pred_block->successors.insert(final_target);
                cfg->blocks[final_target]->predecessors.insert(pred_id);
                cfg->edges[{pred_id, final_target}] = et;
            }
            changes++;
        }
    }
    return changes;
}

DeobfuscationResult Deobfuscator::run_dead_branch_elimination() {
    perform_constant_propagation();

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
        Opcode op = static_cast<Opcode>(last_instr.opcode);
        if (conditional_ops.count(op)) {
            std::vector<int> succs(block->successors.begin(), block->successors.end());
            if (succs.size() == 2) {
                int s1 = succs[0], s2 = succs[1];
                bool g1 = garbage.count(s1), g2 = garbage.count(s2);

                // Try to evaluate condition
                bool known_outcome = false;
                bool result = false;

                auto const& regs = block_entry_regs[id];
                std::vector<RegValue> current = regs;
                for (size_t i = 0; i < block->instructions.size() - 1; ++i) {
                    const auto& instr = block->instructions[i];
                    Opcode iop = static_cast<Opcode>(instr.opcode);
                    if (instr.a < 0 || instr.a >= 256) continue;
                    if (iop == Opcode::LOADK) {
                        current[instr.a].state = RegValue::CONSTANT;
                        if (instr.bx >= 0 && instr.bx < (int)proto->constants.size()) {
                            current[instr.a].val = proto->constants[instr.bx];
                        } else {
                            current[instr.a].state = RegValue::UNKNOWN;
                        }
                    } else if (iop == Opcode::LOADBOOL) { current[instr.a].state = RegValue::CONSTANT; current[instr.a].val.type = LuaConstantType::BOOLEAN; current[instr.a].val.value = (instr.b != 0); }
                    else if (iop == Opcode::LOADNIL) { for (int j = instr.a; j <= instr.a + instr.b && j < 256; ++j) { current[j].state = RegValue::CONSTANT; current[j].val.type = LuaConstantType::NIL; } }
                    else if (iop == Opcode::MOVE) { if (instr.b >= 0 && instr.b < 256) current[instr.a] = current[instr.b]; }
                    else if (iop != Opcode::EQ && iop != Opcode::LT && iop != Opcode::LE && iop != Opcode::NEQ && iop != Opcode::GE && iop != Opcode::GT && iop != Opcode::TEST && iop != Opcode::TESTSET && iop != Opcode::JMP && iop != Opcode::FORLOOP && iop != Opcode::TFORLOOP && iop != Opcode::SETTABLE && iop != Opcode::SETTABUP && iop != Opcode::SETUPVAL) {
                        current[instr.a].state = RegValue::MULTIPLE;
                    }
                }

                auto get_val = [&](int reg_or_k) -> std::pair<bool, LuaConstant> {
                    if (ISK(reg_or_k)) {
                        int idx = INDEXK(reg_or_k);
                        if (idx >= 0 && idx < (int)proto->constants.size()) return {true, proto->constants[idx]};
                    } else {
                        if (reg_or_k >= 0 && reg_or_k < 256 && current.size() > reg_or_k && current[reg_or_k].state == RegValue::CONSTANT) return {true, current[reg_or_k].val};
                    }
                    return {false, {}};
                };

                if (op == Opcode::EQ || op == Opcode::LT || op == Opcode::LE || op == Opcode::NEQ || op == Opcode::GE || op == Opcode::GT) {
                    auto [bk, vb] = get_val(last_instr.b);
                    auto [ck, vc] = get_val(last_instr.c);
                    if (bk && ck && vb.type == vc.type) {
                        known_outcome = true;
                        if (vb.type == LuaConstantType::NUMBER) result = (std::get<double>(vb.value) == std::get<double>(vc.value));
                        else if (vb.type == LuaConstantType::INT) result = (std::get<int64_t>(vb.value) == std::get<int64_t>(vc.value));
                        else if (vb.type == LuaConstantType::BOOLEAN) result = (std::get<bool>(vb.value) == std::get<bool>(vc.value));
                        else if (vb.type == LuaConstantType::STRING) result = (std::get<std::string>(vb.value) == std::get<std::string>(vc.value));
                        else if (vb.type == LuaConstantType::NIL) result = true;

                        if (op == Opcode::EQ) {
                        } else if (op == Opcode::NEQ) {
                            result = !result;
                        } else if (op == Opcode::LT || op == Opcode::LE || op == Opcode::GE || op == Opcode::GT) {
                            double db = (vb.type == LuaConstantType::INT) ? (double)std::get<int64_t>(vb.value) : std::get<double>(vb.value);
                            double dc = (vc.type == LuaConstantType::INT) ? (double)std::get<int64_t>(vc.value) : std::get<double>(vc.value);
                            if (op == Opcode::LT) result = (db < dc);
                            else if (op == Opcode::LE) result = (db <= dc);
                            else if (op == Opcode::GE) result = (db >= dc);
                            else if (op == Opcode::GT) result = (db > dc);
                        }
                        result = (result != (last_instr.a != 0));
                    }
                } else if (op == Opcode::TEST || op == Opcode::TESTSET) {
                    auto [ak, va] = get_val(op == Opcode::TEST ? last_instr.a : last_instr.b);
                    if (ak) {
                        known_outcome = true;
                        bool cond = (va.type != LuaConstantType::NIL && (va.type != LuaConstantType::BOOLEAN || std::get<bool>(va.value)));
                        result = (cond == (last_instr.c != 0));
                    }
                }

                if (known_outcome) {
                    int valid_succ = -1;
                    int garbage_succ = -1;
                    for (int s : succs) {
                        if (cfg->edges[{id, s}] == (result ? EdgeType::COND_TRUE : EdgeType::COND_FALSE)) valid_succ = s;
                        else garbage_succ = s;
                    }
                    if (valid_succ != -1 && garbage_succ != -1) {
                        g1 = (s1 == garbage_succ);
                        g2 = (s2 == garbage_succ);
                    }
                }

                if ((g1 && !g2) || (!g1 && g2)) {
                    int valid_succ = g1 ? s2 : s1;
                    int garbage_succ = g1 ? s1 : s2;

                    Opcode op = static_cast<Opcode>(last_instr.opcode);
                    if (op == Opcode::TESTSET) {
                        EdgeType et = cfg->edges[{id, valid_succ}];
                        if (et == EdgeType::COND_FALSE) {
                            last_instr = Instruction::encode_new(static_cast<int>(Opcode::MOVE), proto->version, last_instr.a, last_instr.b);
                        } else {
                            block->instructions.pop_back();
                        }
                    } else if (op == Opcode::TEST || op == Opcode::EQ || op == Opcode::LT || op == Opcode::LE || op == Opcode::NEQ || op == Opcode::GE || op == Opcode::GT) {
                        block->instructions.pop_back();
                    } else if (op == Opcode::FORLOOP) {
                        int a = last_instr.a;
                        EdgeType et = cfg->edges[{id, valid_succ}];
                        block->instructions.pop_back();
                        if (et == EdgeType::LOOP_BACK) {
                            block->instructions.push_back(Instruction::encode_new(static_cast<int>(Opcode::ADD), a, a, a + 2));
                            block->instructions.push_back(Instruction::encode_new(static_cast<int>(Opcode::MOVE), a + 3, a));
                        } else {
                            block->instructions.push_back(Instruction::encode_new(static_cast<int>(Opcode::ADD), a, a, a + 2));
                        }
                    } else if (op == Opcode::TFORLOOP) {
                        int a = last_instr.a;
                        EdgeType et = cfg->edges[{id, valid_succ}];
                        block->instructions.pop_back();
                        if (et == EdgeType::LOOP_BACK) {
                            block->instructions.push_back(Instruction::encode_new(static_cast<int>(Opcode::MOVE), a, a + 1));
                        }
                    }

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
    int changes = simplify_jmp_chains();
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

DeobfuscationResult Deobfuscator::run_control_flow_deflattening() {
    perform_constant_propagation();
    int changes = 0;

    bool changed = true;
    while (changed) {
        changed = false;

        for (auto const& [id, block] : cfg->blocks) {
            if (block->successors.size() != 1) continue;
            if (block->instructions.empty()) continue;

            Opcode last_op = static_cast<Opcode>(block->instructions.back().opcode);
            int next_id = *block->successors.begin();

            auto exit_regs = block_exit_regs[id];
            int current_id = next_id;
            std::set<int> visited;
            bool valid_trace = true;

            while (true) {
                if (visited.count(current_id)) { valid_trace = false; break; }
                visited.insert(current_id);
                auto current_block = cfg->blocks[current_id];

                if (current_block->instructions.empty()) break;

                auto& instr = current_block->instructions.back();
                Opcode op = static_cast<Opcode>(instr.opcode);

                // Allow only JMP or conditional checks as dispatcher blocks
                if (current_block->instructions.size() > 1) {
                    break;
                }

                if (op == Opcode::JMP) {
                    if (current_block->successors.size() == 1) {
                        current_id = *current_block->successors.begin();
                        continue;
                    } else break;
                }

                std::set<Opcode> conditional_ops = {Opcode::EQ, Opcode::LT, Opcode::LE, Opcode::NEQ, Opcode::GE, Opcode::GT, Opcode::TEST, Opcode::TESTSET};
                if (conditional_ops.count(op) && current_block->successors.size() == 2) {
                    bool known_outcome = false;
                    bool result = false;

                    auto get_val = [&](int reg_or_k) -> std::pair<bool, LuaConstant> {
                        if (ISK(reg_or_k)) {
                            int idx = INDEXK(reg_or_k);
                            if (idx >= 0 && idx < (int)proto->constants.size()) return {true, proto->constants[idx]};
                        } else {
                            if (reg_or_k >= 0 && reg_or_k < 256 && exit_regs.size() > reg_or_k && exit_regs[reg_or_k].state == RegValue::CONSTANT) return {true, exit_regs[reg_or_k].val};
                        }
                        return {false, {}};
                    };

                    if (op == Opcode::EQ || op == Opcode::LT || op == Opcode::LE || op == Opcode::NEQ || op == Opcode::GE || op == Opcode::GT) {
                        auto [bk, vb] = get_val(instr.b);
                        auto [ck, vc] = get_val(instr.c);
                        if (bk && ck && vb.type == vc.type) {
                            known_outcome = true;
                            if (vb.type == LuaConstantType::NUMBER) result = (std::get<double>(vb.value) == std::get<double>(vc.value));
                            else if (vb.type == LuaConstantType::INT) result = (std::get<int64_t>(vb.value) == std::get<int64_t>(vc.value));
                            else if (vb.type == LuaConstantType::BOOLEAN) result = (std::get<bool>(vb.value) == std::get<bool>(vc.value));
                            else if (vb.type == LuaConstantType::STRING) result = (std::get<std::string>(vb.value) == std::get<std::string>(vc.value));
                            else if (vb.type == LuaConstantType::NIL) result = true;

                            if (op == Opcode::EQ) {
                            } else if (op == Opcode::NEQ) {
                                result = !result;
                            } else if (op == Opcode::LT || op == Opcode::LE || op == Opcode::GE || op == Opcode::GT) {
                                double db = (vb.type == LuaConstantType::INT) ? (double)std::get<int64_t>(vb.value) : std::get<double>(vb.value);
                                double dc = (vc.type == LuaConstantType::INT) ? (double)std::get<int64_t>(vc.value) : std::get<double>(vc.value);
                                if (op == Opcode::LT) result = (db < dc);
                                else if (op == Opcode::LE) result = (db <= dc);
                                else if (op == Opcode::GE) result = (db >= dc);
                                else if (op == Opcode::GT) result = (db > dc);
                            }
                            result = (result != (instr.a != 0));
                        }
                    } else if (op == Opcode::TEST || op == Opcode::TESTSET) {
                        auto [ak, va] = get_val(op == Opcode::TEST ? instr.a : instr.b);
                        if (ak) {
                            known_outcome = true;
                            bool cond = (va.type != LuaConstantType::NIL && (va.type != LuaConstantType::BOOLEAN || std::get<bool>(va.value)));
                            result = (cond == (instr.c != 0));
                        }
                    }

                    if (known_outcome) {
                        int next_target = -1;
                        for (int s : current_block->successors) {
                            if (cfg->edges[{current_id, s}] == (result ? EdgeType::COND_TRUE : EdgeType::COND_FALSE)) {
                                next_target = s;
                                break;
                            }
                        }
                        if (next_target != -1) {
                            current_id = next_target;
                            continue;
                        }
                    }
                }

                break;
            }

            if (valid_trace && current_id != next_id && current_id != id) {
                cfg->edges.erase({id, next_id});
                cfg->blocks[id]->successors.erase(next_id);
                cfg->blocks[next_id]->predecessors.erase(id);

                cfg->blocks[id]->successors.insert(current_id);
                cfg->blocks[current_id]->predecessors.insert(id);
                cfg->edges[{id, current_id}] = EdgeType::JUMP;

                if (last_op != Opcode::JMP) {
                    block->instructions.push_back(Instruction::encode_new(static_cast<int>(Opcode::JMP), 0, 0, 0, 0, 0));
                }

                changes++;
                changed = true;
                break;
            }
        }
    }

    if (changes > 0) rebuild_from_cfg();
    return {true, "Control Flow Deflattening", changes, "Deflattened " + std::to_string(changes) + " branches."};
}

DeobfuscationResult Deobfuscator::run_redundant_store_elimination() {
    if (!cfg) cfg = std::make_unique<CFG>(proto);
    int changes = 0;

    for (auto& [id, block] : cfg->blocks) {
        if (block->instructions.empty()) continue;

        std::vector<bool> used_later(256, true);
        for (int i = block->instructions.size() - 1; i >= 0; --i) {
            auto& instr = block->instructions[i];
            Opcode op = static_cast<Opcode>(instr.opcode);

            bool is_redundant = false;
            if (instr.a >= 0 && instr.a < 256 && (op == Opcode::LOADK || op == Opcode::LOADKX || op == Opcode::LOADBOOL)) {
                if (!used_later[instr.a]) {
                    is_redundant = true;
                }
            }

            if (is_redundant) {
                // Remove instruction
                block->instructions.erase(block->instructions.begin() + i);
                changes++;
                continue;
            }

            // Mark reads as used
            auto mode = get_opcode_mode(static_cast<int>(op));
            if (op == Opcode::MOVE && instr.b >= 0 && instr.b < 256) used_later[instr.b] = true;
            if (mode == OpMode::iABC) {
                if (op != Opcode::LOADK && op != Opcode::LOADKX && op != Opcode::LOADBOOL && op != Opcode::MOVE && op != Opcode::LOADNIL && op != Opcode::GETUPVAL && op != Opcode::GETTABUP && op != Opcode::GETTABLE && op != Opcode::NEWTABLE && op != Opcode::SELF) {
                    if (instr.a >= 0 && instr.a < 256) used_later[instr.a] = true;
                }
                if (instr.b >= 0 && instr.b < 256 && !ISK(instr.b)) used_later[instr.b] = true;
                if (instr.c >= 0 && instr.c < 256 && !ISK(instr.c)) used_later[instr.c] = true;
            } else if (mode == OpMode::iABx || mode == OpMode::iAsBx) {
                if (op == Opcode::TEST || op == Opcode::TESTSET || op == Opcode::TFORCALL || op == Opcode::TFORLOOP) {
                    if (instr.a >= 0 && instr.a < 256) used_later[instr.a] = true;
                }
            }

            // Mark writes as overwritten
            if (op == Opcode::LOADK || op == Opcode::LOADKX || op == Opcode::LOADBOOL || op == Opcode::MOVE || op == Opcode::GETUPVAL || op == Opcode::GETTABUP || op == Opcode::GETTABLE || op == Opcode::NEWTABLE) {
                if (instr.a >= 0 && instr.a < 256) used_later[instr.a] = false;
            }
        }
    }

    if (changes > 0) rebuild_from_cfg();
    return {true, "Redundant Store Elimination", changes, "Eliminated " + std::to_string(changes) + " redundant stores"};
}

DeobfuscationResult Deobfuscator::run_conditional_branch_normalization() {
    if (!cfg) cfg = std::make_unique<CFG>(proto);
    int changes = 0;

    std::set<Opcode> conditional_ops = {Opcode::EQ, Opcode::LT, Opcode::LE, Opcode::NEQ, Opcode::GE, Opcode::GT, Opcode::TEST, Opcode::TESTSET};

    // First: Normalize branches where TRUE and FALSE paths converge to the EXACT same block immediately.
    for (auto& [id, block] : cfg->blocks) {
        if (block->instructions.empty()) continue;
        auto& last_instr = block->instructions.back();
        Opcode op = static_cast<Opcode>(last_instr.opcode);

        if (conditional_ops.count(op) && block->successors.size() == 2) {
            std::vector<int> succs(block->successors.begin(), block->successors.end());
            int s1 = succs[0];
            int s2 = succs[1];

            std::set<int> visited;
            int target1 = find_jmp_chain_target(s1, visited);
            visited.clear();
            int target2 = find_jmp_chain_target(s2, visited);

            if (target1 == target2 && target1 != -1) {
                if (op == Opcode::TESTSET) {
                    last_instr = Instruction::encode_new(static_cast<int>(Opcode::MOVE), last_instr.a, last_instr.b);
                } else {
                    block->instructions.pop_back();
                }

                // Keep only one successor, effectively making it sequential to the target or jump
                // Usually the next block in PC is a JMP to target, or simply the target.
                // We'll rewrite the edges: point id directly to target1 as a JUMP.
                block->successors.erase(s1);
                block->successors.erase(s2);
                cfg->blocks[s1]->predecessors.erase(id);
                cfg->blocks[s2]->predecessors.erase(id);
                cfg->edges.erase({id, s1});
                cfg->edges.erase({id, s2});

                block->successors.insert(target1);
                cfg->blocks[target1]->predecessors.insert(id);
                cfg->edges[{id, target1}] = EdgeType::JUMP;

                // Add an explicit JMP instruction to maintain correct output
                int diff = 0; // The rebuild_code method recalculates JMP offsets based on block IDs
                block->instructions.push_back(Instruction::encode_new(static_cast<int>(Opcode::JMP), 0, 0, 0, diff, 0));

                changes++;
            }
        }
    }

    if (changes > 0) rebuild_from_cfg();
    return {true, "Conditional Branch Normalization", changes, "Normalized " + std::to_string(changes) + " conditional branch(es)"};
}

std::vector<DeobfuscationResult> Deobfuscator::run_all_passes(int max_iterations) {
    std::vector<DeobfuscationResult> all_results;
    for (int i = 0; i < max_iterations; ++i) {
        int changes_this_round = 0;

        auto res = run_constant_folding();
        all_results.push_back(res);
        changes_this_round += res.changes_made;

        res = run_constant_propagation();
        all_results.push_back(res);

        res = run_dead_branch_elimination();
        all_results.push_back(res);
        changes_this_round += res.changes_made;

        res = run_dead_code_elimination();
        all_results.push_back(res);
        changes_this_round += res.changes_made;

        res = run_sequential_block_merging();
        all_results.push_back(res);
        changes_this_round += res.changes_made;

        res = run_control_flow_deflattening();
        all_results.push_back(res);
        changes_this_round += res.changes_made;

        if (changes_this_round == 0) break;
    }
    return all_results;
}

} // namespace lua_deobfuscator
