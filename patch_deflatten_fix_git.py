import re

with open("src/lua_deobfuscator/Deobfuscator.cpp", "r") as f:
    content = f.read()

new_logic = """DeobfuscationResult Deobfuscator::run_control_flow_deflattening() {
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
                            if (reg_or_k >= 0 && reg_or_k < 256 && exit_regs[reg_or_k].state == RegValue::CONSTANT) return {true, exit_regs[reg_or_k].val};
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
}"""

content = re.sub(r'DeobfuscationResult Deobfuscator::run_control_flow_deflattening\(\) \{.*?(?=std::vector<DeobfuscationResult>)', new_logic + '\n\n', content, flags=re.DOTALL)

with open("src/lua_deobfuscator/Deobfuscator.cpp", "w") as f:
    f.write(content)


with open("src/main.cpp", "r") as f:
    main_content = f.read()

if "void process_prototype(std::shared_ptr<Prototype> proto" not in main_content:
    idx = main_content.find("using namespace lua_deobfuscator;") + len("using namespace lua_deobfuscator;")
    main_content = main_content[:idx] + "\n\nvoid process_prototype(std::shared_ptr<Prototype> proto, bool fold, bool dbe, bool sbm, bool dce, bool deflatten) {\n    Deobfuscator deob(proto);\n    for (int i = 0; i < 10; ++i) {\n        int changes = 0;\n        if (fold) changes += deob.run_constant_folding().changes_made;\n        if (dbe) changes += deob.run_dead_branch_elimination().changes_made;\n        if (sbm) changes += deob.run_sequential_block_merging().changes_made;\n        if (dce) changes += deob.run_dead_code_elimination().changes_made;\n        if (deflatten) changes += deob.run_control_flow_deflattening().changes_made;\n        if (fold || dbe || deflatten) deob.run_constant_propagation();\n        if (changes == 0 && i > 0) break;\n    }\n    for (auto child : proto->protos) {\n        process_prototype(child, fold, dbe, sbm, dce, deflatten);\n    }\n}" + main_content[idx:]

main_content = re.sub(r'Deobfuscator deob\(chunk\.main\);\s*deob\.run_all_passes\(10\);', 'process_prototype(chunk.main, true, true, true, true, true);', main_content)
main_content = re.sub(r'        // Run optimizations in a loop if any are selected, to ensure interdependent passes settle\n        if \(fold \|\| dbe \|\| sbm \|\| dce \|\| deflatten\) \{\n            for \(int i = 0; i < 10; \+\+i\) \{\n                int changes = 0;\n                if \(fold\) changes \+= deob.run_constant_folding\(\)\.changes_made;\n                if \(dbe\) changes \+= deob.run_dead_branch_elimination\(\)\.changes_made;\n                if \(sbm\) changes \+= deob.run_sequential_block_merging\(\)\.changes_made;\n                if \(dce\) changes \+= deob.run_dead_code_elimination\(\)\.changes_made;\n                if \(deflatten\) changes \+= deob.run_control_flow_deflattening\(\)\.changes_made;\n\n                // Constant propagation doesn\'t return changes_made but is needed for DBE\n                if \(fold \|\| dbe \|\| deflatten\) deob.run_constant_propagation\(\);\n\n                if \(changes == 0 && i > 0\) break;\n            \}\n        \}', '        if (fold || dbe || sbm || dce || deflatten) {\n            process_prototype(chunk.main, fold, dbe, sbm, dce, deflatten);\n        }', main_content)

with open("src/main.cpp", "w") as f:
    f.write(main_content)
