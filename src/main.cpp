#include "lua_deobfuscator/Parser.h"
#include "lua_deobfuscator/Serializer.h"
#include "lua_deobfuscator/Disassembler.h"
#include "lua_deobfuscator/Deobfuscator.h"
#include "lua_deobfuscator/Assembler.h"
#ifdef EMSCRIPTEN
#include <emscripten/bind.h>
#endif
#include <iostream>
#include <fstream>
#include <vector>
#include <cstring>

using namespace lua_deobfuscator;

void process_prototype_target(std::shared_ptr<Prototype> proto, int target_func_id, int& current_id, bool fold, bool dbe, bool sbm, bool dce, bool deflatten, bool rse, bool norm) {
    int func_id = current_id;
    current_id++;
    bool is_target = (target_func_id == -1 || func_id == target_func_id);
    if (is_target) {
        Deobfuscator deob(proto);
        for (int i = 0; i < 10; ++i) {
            int changes = 0;
            if (fold) changes += deob.run_constant_folding().changes_made;
            if (dbe) changes += deob.run_dead_branch_elimination().changes_made;
            if (sbm) changes += deob.run_sequential_block_merging().changes_made;
            if (dce) changes += deob.run_dead_code_elimination().changes_made;
            if (deflatten) changes += deob.run_control_flow_deflattening().changes_made;
            if (rse) changes += deob.run_redundant_store_elimination().changes_made;
            if (norm) changes += deob.run_conditional_branch_normalization().changes_made;
            if (fold || dbe || deflatten || norm) deob.run_constant_propagation();
            if (changes == 0 && i > 0) break;
        }
    }
    for (auto child : proto->protos) {
        process_prototype_target(child, target_func_id, current_id, fold, dbe, sbm, dce, deflatten, rse, norm);
    }
}

void process_prototype(std::shared_ptr<Prototype> proto, bool fold, bool dbe, bool sbm, bool dce, bool deflatten, bool rse, bool norm) {
    int current_id = 0;
    process_prototype_target(proto, -1, current_id, fold, dbe, sbm, dce, deflatten, rse, norm);
}

void print_help() {
    std::cout << "Usage: lua_deobfuscator_cpp <input> [options]" << std::endl;
    std::cout << "Options:" << std::endl;
    std::cout << "  -d, --disassemble    Disassemble the bytecode" << std::endl;
    std::cout << "  -a, --assemble       Assemble the .lasm file" << std::endl;
    std::cout << "  -o <output>          Output file" << std::endl;
    std::cout << "  --deobfuscate        Run all deobfuscation passes" << std::endl;
}

int main(int argc, char** argv) {
    if (argc < 2) {
        print_help();
        return 1;
    }

    std::string input_path = argv[1];
    std::string output_path = "";
    bool do_disassemble = false;
    bool do_deobfuscate = false;
    bool do_assemble = false;

    for (int i = 2; i < argc; ++i) {
        if (std::strcmp(argv[i], "-d") == 0 || std::strcmp(argv[i], "--disassemble") == 0) do_disassemble = true;
        else if (std::strcmp(argv[i], "-a") == 0 || std::strcmp(argv[i], "--assemble") == 0) do_assemble = true;
        else if (std::strcmp(argv[i], "-o") == 0 && i + 1 < argc) output_path = argv[++i];
        else if (std::strcmp(argv[i], "--deobfuscate") == 0) do_deobfuscate = true;
    }

    if (do_assemble) {
        std::ifstream file(input_path);
        if (!file) {
            std::cerr << "Could not open " << input_path << std::endl;
            return 1;
        }
        std::string content((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        try {
            LuaChunk chunk = Assembler::assemble(content);
            if (!output_path.empty()) {
                auto serialized = Serializer::serialize(chunk);
                std::ofstream out_file(output_path, std::ios::binary);
                out_file.write(reinterpret_cast<const char*>(serialized.data()), serialized.size());
                std::cout << "Wrote assembled bytecode to " << output_path << std::endl;
            }
        } catch (const std::exception& e) {
            std::cerr << "Error during assembly: " << e.what() << std::endl;
            return 1;
        }
        return 0;
    }

    std::ifstream file(input_path, std::ios::binary);
    if (!file) {
        std::cerr << "Could not open " << input_path << std::endl;
        return 1;
    }
    std::vector<uint8_t> data((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());

    try {
        LuaChunk chunk = Parser::parse(data);

        if (do_deobfuscate) {
            process_prototype(chunk.main, true, true, true, true, true, true, true);
        }

        if (do_disassemble) {
            Disassembler disasm(chunk);
            std::cout << disasm.disassemble() << std::endl;
        }

        if (!output_path.empty()) {
            auto serialized = Serializer::serialize(chunk);
            std::ofstream out_file(output_path, std::ios::binary);
            out_file.write(reinterpret_cast<const char*>(serialized.data()), serialized.size());
            std::cout << "Wrote processed bytecode to " << output_path << std::endl;
        }
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}

#ifdef EMSCRIPTEN
#include <emscripten/val.h>

using namespace emscripten;

std::string escape_json_string(const std::string& input) {
    std::string output;
    for (char c : input) {
        if (c == '"') output += "\\\"";
        else if (c == '\\') output += "\\\\";
        else if (c == '\b') output += "\\b";
        else if (c == '\f') output += "\\f";
        else if (c == '\n') output += "\\n";
        else if (c == '\r') output += "\\r";
        else if (c == '\t') output += "\\t";
        else output += c;
    }
    return output;
}

std::string build_structure(std::shared_ptr<lua_deobfuscator::Prototype> proto) {
    std::stringstream ss;
    ss << "{";
    ss << "\"source\": \"" << escape_json_string(proto->source) << "\",";
    ss << "\"line_defined\": " << proto->line_defined << ",";
    ss << "\"last_line_defined\": " << proto->last_line_defined << ",";
    ss << "\"num_params\": " << proto->num_params << ",";
    ss << "\"is_vararg\": " << proto->is_vararg << ",";
    ss << "\"max_stack_size\": " << proto->max_stack_size << ",";
    ss << "\"num_instructions\": " << proto->code.size() << ",";

    ss << "\"constants\": [";
    for (size_t i = 0; i < proto->constants.size(); ++i) {
        ss << "\"" << escape_json_string(lua_deobfuscator::Disassembler::format_constant(proto->constants[i])) << "\"";
        if (i < proto->constants.size() - 1) ss << ",";
    }
    ss << "],";

    ss << "\"upvalues\": [";
    for (size_t i = 0; i < proto->upvalues.size(); ++i) {
        ss << "{";
        ss << "\"name\": \"" << escape_json_string(proto->upvalues[i].name) << "\",";
        ss << "\"instack\": " << (proto->upvalues[i].instack ? "true" : "false") << ",";
        ss << "\"idx\": " << proto->upvalues[i].idx;
        ss << "}";
        if (i < proto->upvalues.size() - 1) ss << ",";
    }
    ss << "],";

    ss << "\"locvars\": [";
    for (size_t i = 0; i < proto->locvars.size(); ++i) {
        ss << "{";
        ss << "\"varname\": \"" << escape_json_string(proto->locvars[i].varname) << "\",";
        ss << "\"startpc\": " << proto->locvars[i].startpc << ",";
        ss << "\"endpc\": " << proto->locvars[i].endpc;
        ss << "}";
        if (i < proto->locvars.size() - 1) ss << ",";
    }
    ss << "],";

    ss << "\"protos\": [";
    for (size_t i = 0; i < proto->protos.size(); ++i) {
        ss << build_structure(proto->protos[i]);
        if (i < proto->protos.size() - 1) ss << ",";
    }
    ss << "]";

    ss << "}";
    return ss.str();
}

struct DeobResultJS {
    bool success;
    std::string disassembly;
    std::string dot;
    std::string structure;
    emscripten::val bytecode;
    std::string error;
};

DeobResultJS deobfuscate_wasm(emscripten::val input, int target_func_id, bool fold, bool dbe, bool sbm, bool dce, bool deflatten, bool rse, bool norm) {
    try {
        auto l = input["length"].as<unsigned>();
        std::vector<uint8_t> data(l);
        for(unsigned i=0; i<l; ++i) data[i] = input[i].as<uint8_t>();

        LuaChunk chunk = Parser::parse(data);

        if (fold || dbe || sbm || dce || deflatten || rse || norm) {
            int current_id = 0;
            process_prototype_target(chunk.main, target_func_id, current_id, fold, dbe, sbm, dce, deflatten, rse, norm);
        }

        Disassembler disasm(chunk);
        CFG cfg(chunk.main);

        auto serialized = Serializer::serialize(chunk);
        emscripten::val bytecode = emscripten::val::global("Uint8Array").new_(emscripten::typed_memory_view(serialized.size(), serialized.data()));

        std::string structure_json = build_structure(chunk.main);

        return {true, disasm.disassemble(), cfg.to_dot(), structure_json, bytecode, ""};
    } catch (const std::exception& e) {
        return {false, "", "", "", emscripten::val::null(), e.what()};
    }
}

DeobResultJS assemble_wasm(std::string lasm) {
    try {
        LuaChunk chunk = Assembler::assemble(lasm);
        auto serialized = Serializer::serialize(chunk);
        emscripten::val bytecode = emscripten::val::global("Uint8Array").new_(emscripten::typed_memory_view(serialized.size(), serialized.data()));
        return {true, "", "", "", bytecode, ""};
    } catch (const std::exception& e) {
        return {false, "", "", "", emscripten::val::null(), e.what()};
    }
}

EMSCRIPTEN_BINDINGS(lua_deobfuscator) {
    value_object<DeobResultJS>("DeobResult")
        .field("success", &DeobResultJS::success)
        .field("disassembly", &DeobResultJS::disassembly)
        .field("dot", &DeobResultJS::dot)
        .field("structure", &DeobResultJS::structure)
        .field("bytecode", &DeobResultJS::bytecode)
        .field("error", &DeobResultJS::error);

    function("deobfuscate", &deobfuscate_wasm);
    function("assemble", &assemble_wasm);
}
#endif
