#include "Assembler.h"
#include <sstream>
#include <iostream>
#include <map>
#include <algorithm>
#include <regex>

namespace lua_deobfuscator {

static std::map<std::string, Opcode> opcode_map;
static void init_opcode_map() {
    if (!opcode_map.empty()) return;
    for (int i = 0; i < 64; ++i) {
        Opcode op = static_cast<Opcode>(i);
        std::string name = get_opcode_name(op);
        if (name.substr(0, 8) != "UNKNOWN_") {
            opcode_map[name] = op;
        }
    }
}

Assembler::Assembler(const std::string& lasm) : lasm(lasm) {
    init_opcode_map();
}

LuaChunk Assembler::assemble(const std::string& lasm) {
    Assembler assem(lasm);
    return assem.do_assemble();
}

std::vector<Assembler::Token> Assembler::tokenize() {
    std::vector<Token> tokens;
    std::stringstream ss(lasm);
    std::string line;
    int line_num = 0;

    while (std::getline(ss, line)) {
        line_num++;
        size_t semi = line.find(';');
        std::string content = (semi == std::string::npos) ? line : line.substr(0, semi);

        content.erase(0, content.find_first_not_of(" \t\r\n"));
        content.erase(content.find_last_not_of(" \t\r\n") + 1, std::string::npos);

        if (content.empty()) continue;

        std::vector<std::string> parts;
        std::string current;
        bool in_string = false;
        for (size_t i = 0; i < content.size(); ++i) {
            char c = content[i];
            if (c == '"') {
                in_string = !in_string;
                current += c;
            } else if (!in_string && (c == ' ' || c == '\t')) {
                if (!current.empty()) {
                    parts.push_back(current);
                    current.clear();
                }
            } else {
                current += c;
            }
        }
        if (!current.empty()) parts.push_back(current);

        for (const auto& p : parts) {
            Token t;
            t.line = line_num;
            t.value = p;
            if (p[0] == '.') t.type = Token::DIRECTIVE;
            else if (p[0] == ':') t.type = Token::LABEL;
            else if (p[0] == '"') t.type = Token::CONSTANT;
            else if (p == "true" || p == "false" || p == "nil") t.type = Token::CONSTANT;
            else if (p[0] == 'v' && p.size() > 1 && isdigit(p[1])) t.type = Token::REGISTER;
            else if (p[0] == 'u' && p.size() > 1 && isdigit(p[1])) t.type = Token::UPVAL;
            else if (p[0] == 'K' && p.size() > 1 && isdigit(p[1])) t.type = Token::CONSTANT;
            else if (opcode_map.count(p)) t.type = Token::INSTRUCTION;
            else if ((isdigit(p[0]) || (p[0] == '-' && p.size() > 1 && (isdigit(p[1]) || p[1] == '.'))) && p.find_first_not_of("-0123456789.") == std::string::npos) t.type = Token::NUMBER;
            else t.type = Token::IDENTIFIER;
            tokens.push_back(t);
        }
        tokens.push_back({Token::NEWLINE, "", line_num});
    }
    tokens.push_back({Token::END_OF_FILE, "", line_num});
    return tokens;
}

LuaChunk Assembler::do_assemble() {
    auto tokens = tokenize();
    auto it = tokens.begin();

    LuaChunk chunk;
    chunk.header.signature = {0x1b, 0x4c, 0x75, 0x61};
    chunk.header.version = 0x52;
    chunk.header.format = 0;
    chunk.header.endianness = 1;
    chunk.header.size_int = 4;
    chunk.header.size_size_t = 4;
    chunk.header.size_instruction = 4;
    chunk.header.size_lua_number = 8;
    chunk.header.integral_flag = 0;
    chunk.header.tail = {0x19, 0x93, 0x0d, 0x0a, 0x1a, 0x0a};

    chunk.main = parse_prototype(it, tokens.end());

    return chunk;
}

std::shared_ptr<Prototype> Assembler::parse_prototype(std::vector<Token>::iterator& it, const std::vector<Token>::iterator& end) {
    auto proto = std::make_shared<Prototype>();
    std::map<std::string, int> labels;
    struct JumpFixup {
        int pc;
        std::string label;
    };
    std::vector<JumpFixup> fixups;

    auto add_constant = [&](const Token& t) -> int {
        if (t.type == Token::CONSTANT && t.value.size() > 1 && t.value[0] == 'K' && isdigit(t.value[1])) {
             return std::stoi(t.value.substr(1));
        }

        LuaConstant c;
        if (t.type == Token::CONSTANT) {
            if (t.value[0] == '"') {
                c.type = LuaConstantType::STRING;
                c.value = t.value.substr(1, t.value.size() - 2);
            } else if (t.value == "true") {
                c.type = LuaConstantType::BOOLEAN;
                c.value = true;
            } else if (t.value == "false") {
                c.type = LuaConstantType::BOOLEAN;
                c.value = false;
            } else if (t.value == "nil") {
                c.type = LuaConstantType::NIL;
                c.value = std::monostate{};
            } else {
                if (t.value.find('.') != std::string::npos) {
                    c.type = LuaConstantType::NUMBER;
                    c.value = std::stod(t.value);
                } else {
                    c.type = LuaConstantType::INT;
                    c.value = static_cast<int64_t>(std::stoll(t.value));
                }
            }
        } else if (t.type == Token::NUMBER) {
            if (t.value.find('.') != std::string::npos) {
                c.type = LuaConstantType::NUMBER;
                c.value = std::stod(t.value);
            } else {
                c.type = LuaConstantType::INT;
                c.value = static_cast<int64_t>(std::stoll(t.value));
            }
        }

        for (size_t i = 0; i < proto->constants.size(); ++i) {
            if (proto->constants[i].type == c.type) {
                 if (c.type == LuaConstantType::STRING) {
                     if (std::holds_alternative<std::string>(proto->constants[i].value) && std::get<std::string>(proto->constants[i].value) == std::get<std::string>(c.value)) return (int)i;
                 } else if (c.type == LuaConstantType::BOOLEAN) {
                     if (std::holds_alternative<bool>(proto->constants[i].value) && std::get<bool>(proto->constants[i].value) == std::get<bool>(c.value)) return (int)i;
                 } else if (c.type == LuaConstantType::NUMBER) {
                     if (std::holds_alternative<double>(proto->constants[i].value) && std::get<double>(proto->constants[i].value) == std::get<double>(c.value)) return (int)i;
                 } else if (c.type == LuaConstantType::INT) {
                     if (std::holds_alternative<int64_t>(proto->constants[i].value) && std::get<int64_t>(proto->constants[i].value) == std::get<int64_t>(c.value)) return (int)i;
                 } else if (c.type == LuaConstantType::NIL) return (int)i;
            }
        }
        proto->constants.push_back(c);
        return (int)proto->constants.size() - 1;
    };

    auto parse_rk = [&](const Token& t) -> int {
        if (t.type == Token::REGISTER) return std::stoi(t.value.substr(1));
        if (t.type == Token::CONSTANT && t.value.size() > 1 && t.value[0] == 'K' && isdigit(t.value[1])) return RKASK(std::stoi(t.value.substr(1)));
        return RKASK(add_constant(t));
    };

    while (it != end) {
        if (it->type == Token::DIRECTIVE) {
            if (it->value == ".func") {
                it++;
                while (it != end && it->type != Token::NEWLINE) it++;
                proto->protos.push_back(parse_prototype(it, end));
                if (it != end) it++;
            } else if (it->value == ".end") {
                it++;
                while (it != end && it->type != Token::NEWLINE) it++;
                return proto;
            } else if (it->value == ".source") {
                it++;
                if (it != end && it->type == Token::CONSTANT) {
                    proto->source = it->value.substr(1, it->value.size() - 2);
                    it++;
                }
            } else if (it->value == ".linedefined") {
                it++; if (it != end) { proto->line_defined = std::stoi(it->value); it++; }
            } else if (it->value == ".lastlinedefined") {
                it++; if (it != end) { proto->last_line_defined = std::stoi(it->value); it++; }
            } else if (it->value == ".numparams") {
                it++; if (it != end) { proto->num_params = std::stoi(it->value); it++; }
            } else if (it->value == ".is_vararg") {
                it++; if (it != end) { proto->is_vararg = std::stoi(it->value); it++; }
            } else if (it->value == ".maxstacksize") {
                it++; if (it != end) { proto->max_stack_size = std::stoi(it->value); it++; }
            } else if (it->value == ".upval") {
                it++;
                Upvalue u;
                if (it != end) {
                    if (it->value[0] == 'v') u.instack = true;
                    else u.instack = false;
                    u.idx = std::stoi(it->value.substr(1));
                    it++;
                }
                if (it != end && it->type == Token::CONSTANT) {
                    u.name = it->value.substr(1, it->value.size() - 2);
                    it++;
                }
                proto->upvalues.push_back(u);
            } else if (it->value == ".local") {
                it++;
                LocVar l;
                l.startpc = (int)proto->code.size();
                if (it != end) it++; // skip vIdx
                if (it != end && it->type == Token::CONSTANT) {
                    l.varname = it->value.substr(1, it->value.size() - 2);
                    it++;
                }
                proto->locvars.push_back(l);
            } else if (it->value == ".end") {
                auto next = it + 1;
                if (next != end && next->value == "local") {
                    it += 2;
                    if (it != end) it++; // skip vIdx
                    if (it != end) {
                        std::string name = it->value.substr(1, it->value.size() - 2);
                        for (auto& l : proto->locvars) {
                            if (l.varname == name && l.endpc == 0) {
                                l.endpc = (int)proto->code.size();
                                break;
                            }
                        }
                        it++;
                    }
                } else {
                    return proto;
                }
            } else if (it->value == ".line") {
                it++;
                if (it != end) {
                    int line = std::stoi(it->value);
                    it++;
                    while (proto->lineinfo.size() < proto->code.size()) proto->lineinfo.push_back(line);
                    if (proto->lineinfo.size() == proto->code.size()) proto->lineinfo.push_back(line);
                }
            } else {
                it++;
            }
        } else if (it->type == Token::LABEL) {
            labels[it->value] = (int)proto->code.size();
            it++;
        } else if (it->type == Token::INSTRUCTION) {
            Opcode op = opcode_map[it->value];
            std::string op_name = it->value;
            it++;
            std::vector<Token> args;
            while (it != end && it->type != Token::NEWLINE && it->type != Token::END_OF_FILE) {
                if (it->value == ";" || it->value == "↓" || it->value == "↑") {
                    while (it != end && it->type != Token::NEWLINE) it++;
                    break;
                }
                args.push_back(*it);
                it++;
            }

            Instruction instr;
            instr.a = 0;
            instr.b = 0;
            instr.c = 0;
            instr.bx = 0;
            instr.sbx = 0;
            instr.ax = 0;
            instr.opcode = static_cast<int>(op);
            instr.opcode_name = op_name;
            OpMode mode = get_opcode_mode(op);

            if (op == Opcode::JMP) {
                if (args.size() >= 2 && isdigit(args[0].value[0])) {
                    instr.a = std::stoi(args[0].value);
                    fixups.push_back({static_cast<int>(proto->code.size()), args[1].value});
                } else if (args.size() >= 1) {
                    instr.a = 0;
                    fixups.push_back({static_cast<int>(proto->code.size()), args[0].value});
                }
            } else if (op == Opcode::FORLOOP || op == Opcode::FORPREP || op == Opcode::TFORLOOP) {
                if (args[0].value[0] == 'v' || args[0].value[0] == 'u') instr.a = std::stoi(args[0].value.substr(1));
                else instr.a = std::stoi(args[0].value);
                fixups.push_back({static_cast<int>(proto->code.size()), args[1].value});
            } else if (mode == OpMode::iABC) {
                if (args.size() >= 1) {
                    if (args[0].value[0] == 'v' || args[0].value[0] == 'u') instr.a = std::stoi(args[0].value.substr(1));
                    else instr.a = std::stoi(args[0].value);
                }
                if (args.size() >= 2) {
                    if (op == Opcode::GETUPVAL || op == Opcode::SETUPVAL || op == Opcode::GETTABUP) {
                        if (args[1].value[0] == 'u') instr.b = std::stoi(args[1].value.substr(1));
                        else instr.b = std::stoi(args[1].value);
                    } else if (op == Opcode::SETTABUP) {
                         // A is upvalue, B is RK, C is RK
                         instr.b = parse_rk(args[1]);
                    } else {
                        instr.b = parse_rk(args[1]);
                    }
                }
                if (args.size() >= 3) {
                    instr.c = parse_rk(args[2]);
                }
            } else if (mode == OpMode::iABx) {
                if (args.size() >= 1) {
                    if (args[0].value[0] == 'v' || args[0].value[0] == 'u') instr.a = std::stoi(args[0].value.substr(1));
                    else instr.a = std::stoi(args[0].value);
                }
                if (args.size() >= 2) {
                    if (args[1].value[0] == 'F') {
                        instr.bx = std::stoi(args[1].value.substr(1));
                    } else {
                        instr.bx = add_constant(args[1]);
                    }
                }
            } else if (mode == OpMode::iAsBx) {
                 if (args.size() >= 1) {
                     if (args[0].value[0] == 'v' || args[0].value[0] == 'u') instr.a = std::stoi(args[0].value.substr(1));
                     else instr.a = std::stoi(args[0].value);
                 }
                 if (args.size() >= 2) instr.sbx = std::stoi(args[1].value);
            } else if (mode == OpMode::iAx) {
                if (args.size() >= 1) instr.ax = std::stoi(args[0].value);
            }
            instr = Instruction::encode_new(instr.opcode, proto->version, instr.a, instr.b, instr.c, instr.sbx, instr.ax);
            proto->code.push_back(instr);
        } else {
            it++;
        }
    }

    for (const auto& f : fixups) {
        if (labels.count(f.label)) {
            int target = labels[f.label];
            int sbx = target - f.pc - 1;
            proto->code[f.pc] = Instruction::encode_new(proto->code[f.pc].opcode, proto->version, proto->code[f.pc].a, proto->code[f.pc].b, proto->code[f.pc].c, sbx, proto->code[f.pc].ax);
        }
    }

    while (proto->lineinfo.size() < proto->code.size()) {
        proto->lineinfo.push_back(proto->lineinfo.empty() ? 0 : proto->lineinfo.back());
    }

    return proto;
}

} // namespace lua_deobfuscator
