#include "lua_deobfuscator/Parser.h"
#include "lua_deobfuscator/Serializer.h"
#include "lua_deobfuscator/Disassembler.h"
#include "lua_deobfuscator/Deobfuscator.h"
#include <iostream>
#include <fstream>
#include <vector>
#include <cstring>

using namespace lua_deobfuscator;

void print_help() {
    std::cout << "Usage: lua_deobfuscator_cpp <input.luac> [options]" << std::endl;
    std::cout << "Options:" << std::endl;
    std::cout << "  -d, --disassemble    Disassemble the bytecode" << std::endl;
    std::cout << "  -o <output.luac>     Output the (processed) bytecode" << std::endl;
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

    for (int i = 2; i < argc; ++i) {
        if (std::strcmp(argv[i], "-d") == 0 || std::strcmp(argv[i], "--disassemble") == 0) do_disassemble = true;
        else if (std::strcmp(argv[i], "-o") == 0 && i + 1 < argc) output_path = argv[++i];
        else if (std::strcmp(argv[i], "--deobfuscate") == 0) do_deobfuscate = true;
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
            Deobfuscator deob(chunk.main);
            deob.run_constant_folding();
            deob.run_dead_branch_elimination();
            deob.run_sequential_block_merging();
            deob.run_dead_code_elimination();
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
