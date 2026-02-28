#include "CFG.h"
#include "Disassembler.h"
#include <algorithm>
#include <sstream>

static std::string escape_dot_label(const std::string& str) {
    std::string res;
    for (char c : str) {
        if (c == '"') res += "'";
        else if (c == '\\') res += "\\\\";
        else if (c == '\n') res += "\\n";
        else if (c == '\r') res += "\\r";
        else res += c;
    }
    return res;
}

namespace lua_deobfuscator {

CFG::CFG(std::shared_ptr<Prototype> proto) : proto(proto), block_counter(0) {
    build();
}

void CFG::build() {
    if (proto->code.empty()) return;
    std::set<int> leaders = find_leaders();
    create_blocks(leaders);
    create_edges();
    mark_special_blocks();
}

std::set<int> CFG::find_leaders() {
    std::set<int> leaders;
    leaders.insert(0);
    int n = proto->code.size();

    for (int pc = 0; pc < n; ++pc) {
        Opcode op = static_cast<Opcode>(proto->code[pc].opcode);

        if (op == Opcode::JMP || op == Opcode::FORLOOP || op == Opcode::FORPREP || op == Opcode::TFORLOOP) {
            int target = pc + proto->code[pc].sbx + 1;
            if (target >= 0 && target < n) leaders.insert(target);
        }

        if (op == Opcode::EQ || op == Opcode::LT || op == Opcode::LE || op == Opcode::NEQ ||
            op == Opcode::GE || op == Opcode::GT || op == Opcode::TEST || op == Opcode::TESTSET) {
            if (pc + 1 < n) leaders.insert(pc + 1);
            if (pc + 2 < n) leaders.insert(pc + 2);
        }

        if (op == Opcode::LOADBOOL && proto->code[pc].c != 0) {
            if (pc + 1 < n) leaders.insert(pc + 1);
            if (pc + 2 < n) leaders.insert(pc + 2);
        }

        if ((op == Opcode::SETLIST && proto->code[pc].c == 0) || op == Opcode::LOADKX) {
            if (pc + 1 < n) leaders.insert(pc + 1);
            if (pc + 2 < n) leaders.insert(pc + 2);
        }

        if (op == Opcode::JMP || op == Opcode::RETURN || op == Opcode::TAILCALL || op == Opcode::FORLOOP || op == Opcode::FORPREP || op == Opcode::TFORLOOP) {
            if (pc + 1 < n) leaders.insert(pc + 1);
        }
    }
    return leaders;
}

void CFG::create_blocks(const std::set<int>& leaders) {
    std::vector<int> sorted_leaders(leaders.begin(), leaders.end());
    for (size_t i = 0; i < sorted_leaders.size(); ++i) {
        int start = sorted_leaders[i];
        int end = (i + 1 < sorted_leaders.size()) ? sorted_leaders[i + 1] : proto->code.size();

        auto block = std::make_shared<BasicBlock>();
        block->id = block_counter++;
        block->start_pc = start;
        block->end_pc = end;
        for (int pc = start; pc < end; ++pc) {
            block->instructions.push_back(proto->code[pc]);
            pc_to_block[pc] = block->id;
        }
        blocks[block->id] = block;
    }
}

void CFG::create_edges() {
    for (auto const& [id, block] : blocks) {
        if (block->instructions.empty()) continue;
        int last_pc = block->end_pc - 1;
        const auto& instr = block->instructions.back();
        Opcode op = static_cast<Opcode>(instr.opcode);

        if (op == Opcode::JMP) {
            add_edge(id, last_pc + instr.sbx + 1, EdgeType::JUMP);
        } else if (op == Opcode::EQ || op == Opcode::LT || op == Opcode::LE || op == Opcode::NEQ || op == Opcode::GE || op == Opcode::GT || op == Opcode::TEST || op == Opcode::TESTSET) {
            int next_pc = last_pc + 1;
            int skip_pc = last_pc + 2;
            if (next_pc < (int)proto->code.size()) {
                if (static_cast<Opcode>(proto->code[next_pc].opcode) == Opcode::JMP) {
                    if (skip_pc < (int)proto->code.size()) add_edge(id, skip_pc, EdgeType::COND_TRUE);
                    add_edge(id, next_pc, EdgeType::COND_FALSE);
                } else {
                    add_edge(id, next_pc, EdgeType::COND_FALSE);
                    if (skip_pc < (int)proto->code.size()) add_edge(id, skip_pc, EdgeType::COND_TRUE);
                }
            }
        } else if (op == Opcode::FORLOOP) {
            add_edge(id, last_pc + instr.sbx + 1, EdgeType::LOOP_BACK);
            if (last_pc + 1 < (int)proto->code.size()) add_edge(id, last_pc + 1, EdgeType::LOOP_EXIT);
        } else if (op == Opcode::FORPREP) {
            add_edge(id, last_pc + instr.sbx + 1, EdgeType::JUMP);
        } else if (op == Opcode::TFORLOOP) {
            add_edge(id, last_pc + instr.sbx + 1, EdgeType::LOOP_BACK);
            if (last_pc + 1 < (int)proto->code.size()) add_edge(id, last_pc + 1, EdgeType::LOOP_EXIT);
        } else if (op == Opcode::LOADBOOL && instr.c != 0) {
            if (last_pc + 2 < (int)proto->code.size()) add_edge(id, last_pc + 2, EdgeType::JUMP);
        } else if ((op == Opcode::SETLIST && instr.c == 0) || op == Opcode::LOADKX) {
            if (last_pc + 2 < (int)proto->code.size()) add_edge(id, last_pc + 2, EdgeType::SEQUENTIAL);
        } else if (op == Opcode::RETURN || op == Opcode::TAILCALL) {
            // No exit edges
        } else {
            if (last_pc + 1 < (int)proto->code.size()) add_edge(id, last_pc + 1, EdgeType::SEQUENTIAL);
        }
    }
}

void CFG::add_edge(int from_id, int to_pc, EdgeType type) {
    if (pc_to_block.count(to_pc)) {
        int to_id = pc_to_block[to_pc];
        edges[{from_id, to_id}] = type;
        blocks[from_id]->successors.insert(to_id);
        blocks[to_id]->predecessors.insert(from_id);
    }
}

void CFG::mark_special_blocks() {
    if (pc_to_block.count(0)) blocks[pc_to_block[0]]->is_entry = true;
    for (auto const& [id, block] : blocks) {
        if (block->successors.empty()) block->is_exit = true;
        else if (!block->instructions.empty()) {
            Opcode op = static_cast<Opcode>(block->instructions.back().opcode);
            if (op == Opcode::RETURN || op == Opcode::TAILCALL) block->is_exit = true;
        }
    }
}

std::set<int> CFG::find_unreachable_blocks() {
    std::set<int> reachable;
    int entry_id = -1;
    for (auto const& [id, block] : blocks) if (block->is_entry) { entry_id = id; break; }
    if (entry_id == -1) {
        for (auto const& [id, block] : blocks) reachable.insert(id);
        return {}; // No entry?
    }

    std::vector<int> stack = {entry_id};
    while (!stack.empty()) {
        int id = stack.back();
        stack.pop_back();
        if (reachable.count(id)) continue;
        reachable.insert(id);
        for (int succ : blocks[id]->successors) stack.push_back(succ);
    }

    std::set<int> unreachable;
    for (auto const& [id, block] : blocks) if (!reachable.count(id)) unreachable.insert(id);
    return unreachable;
}

std::vector<Instruction> CFG::rebuild_code() {
    std::vector<int> ordered_ids;
    for (auto const& [id, block] : blocks) ordered_ids.push_back(id);
    std::sort(ordered_ids.begin(), ordered_ids.end(), [&](int a, int b) {
        return blocks[a]->start_pc < blocks[b]->start_pc;
    });

    std::map<int, int> block_new_start;
    int current_pc = 0;
    for (int id : ordered_ids) {
        block_new_start[id] = current_pc;
        current_pc += blocks[id]->instructions.size();
    }

    std::vector<Instruction> new_code;
    for (int id : ordered_ids) {
        auto block = blocks[id];
        for (size_t i = 0; i < block->instructions.size(); ++i) {
            auto instr = block->instructions[i];
            Opcode op = static_cast<Opcode>(instr.opcode);
            int pc = block_new_start[id] + i;

            if (op == Opcode::JMP || op == Opcode::FORLOOP || op == Opcode::FORPREP || op == Opcode::TFORLOOP) {
                // Find target block from edges
                int target_id = -1;
                for (auto const& [edge, type] : edges) {
                    if (edge.first == id && (type == EdgeType::JUMP || type == EdgeType::LOOP_BACK)) {
                        target_id = edge.second;
                        break;
                    }
                }
                if (target_id != -1) {
                    int target_pc = block_new_start[target_id];
                    instr.sbx = target_pc - pc - 1;
                    instr.bx = instr.sbx + 131071;
                    instr.raw = ((instr.opcode & 0x3F) | ((instr.a & 0xFF) << 6) | ((instr.bx & 0x3FFFF) << 14));
                }
            }
            new_code.push_back(instr);
        }
    }
    return new_code;
}

void CFG::remove_block(int block_id) {
    if (!blocks.count(block_id)) return;
    auto block = blocks[block_id];
    for (int succ_id : block->successors) blocks[succ_id]->predecessors.erase(block_id);
    for (int pred_id : block->predecessors) blocks[pred_id]->successors.erase(block_id);

    // Remove edges
    for (auto it = edges.begin(); it != edges.end(); ) {
        if (it->first.first == block_id || it->first.second == block_id) it = edges.erase(it);
        else ++it;
    }

    blocks.erase(block_id);
}

std::string CFG::to_dot(bool include_instructions) {
    std::stringstream ss;
    ss << "digraph CFG {" << std::endl;
    ss << "  node [shape=box];" << std::endl;

    int global_func_id = 0;

    auto dump_cfg = [&](auto& self, std::shared_ptr<Prototype> p, int indent_level) -> void {
        int func_id = global_func_id++;
        std::string ind(indent_level * 2, ' ');
        ss << ind << "subgraph cluster_" << func_id << " {" << std::endl;
        ss << ind << "  label=\"Function " << (func_id == 0 ? "Main" : std::to_string(func_id)) << "\";" << std::endl;
        ss << ind << "  style=dashed;" << std::endl;
        ss << ind << "  color=gray;" << std::endl;

        // If p is the same as this->proto, we just use this->blocks and this->edges
        // otherwise we create a new CFG for the child prototype
        std::set<int> jump_targets = Disassembler::collect_jump_targets(p);

        if (p == this->proto) {
            for (auto const& [id, block] : this->blocks) {
                ss << ind << "  F" << func_id << "_BB" << id << " [label=\"BB" << id << " [PC " << block->start_pc << "-" << (block->end_pc - 1) << "]";
                if (include_instructions) {
                    for (size_t i = 0; i < block->instructions.size(); ++i) {
                        int pc = block->start_pc + i;
                        std::string instr_str = Disassembler::format_instruction(block->instructions[i], p, pc, 0, jump_targets);
                        ss << "\\n" << pc << ": " << escape_dot_label(instr_str);
                    }
                }
                ss << "\"";
                if (block->is_entry) ss << ", style=filled, fillcolor=green";
                else if (block->is_exit) ss << ", style=filled, fillcolor=red";
                ss << "];" << std::endl;
            }

            for (auto const& [edge, type] : this->edges) {
                ss << ind << "  F" << func_id << "_BB" << edge.first << " -> F" << func_id << "_BB" << edge.second;
                if (type == EdgeType::COND_TRUE) ss << " [label=\"T\", color=\"#228B22\"]";
                else if (type == EdgeType::COND_FALSE) ss << " [label=\"F\", color=\"#DC143C\"]";
                else if (type == EdgeType::LOOP_BACK) ss << " [label=\"loop\", style=dashed, color=\"#4169E1\"]";
                else if (type == EdgeType::LOOP_EXIT) ss << " [label=\"exit\"]";
                ss << ";" << std::endl;
            }
        } else {
            CFG child_cfg(p);
            for (auto const& [id, block] : child_cfg.blocks) {
                ss << ind << "  F" << func_id << "_BB" << id << " [label=\"BB" << id << " [PC " << block->start_pc << "-" << (block->end_pc - 1) << "]";
                if (include_instructions) {
                    for (size_t i = 0; i < block->instructions.size(); ++i) {
                        int pc = block->start_pc + i;
                        std::string instr_str = Disassembler::format_instruction(block->instructions[i], p, pc, 0, jump_targets);
                        ss << "\\n" << pc << ": " << escape_dot_label(instr_str);
                    }
                }
                ss << "\"";
                if (block->is_entry) ss << ", style=filled, fillcolor=green";
                else if (block->is_exit) ss << ", style=filled, fillcolor=red";
                ss << "];" << std::endl;
            }

            for (auto const& [edge, type] : child_cfg.edges) {
                ss << ind << "  F" << func_id << "_BB" << edge.first << " -> F" << func_id << "_BB" << edge.second;
                if (type == EdgeType::COND_TRUE) ss << " [label=\"T\", color=\"#228B22\"]";
                else if (type == EdgeType::COND_FALSE) ss << " [label=\"F\", color=\"#DC143C\"]";
                else if (type == EdgeType::LOOP_BACK) ss << " [label=\"loop\", style=dashed, color=\"#4169E1\"]";
                else if (type == EdgeType::LOOP_EXIT) ss << " [label=\"exit\"]";
                ss << ";" << std::endl;
            }
        }

        for (auto child : p->protos) {
            self(self, child, indent_level + 1);
        }

        ss << ind << "}" << std::endl;
    };

    dump_cfg(dump_cfg, this->proto, 1);

    ss << "}" << std::endl;
    return ss.str();
}

} // namespace lua_deobfuscator
