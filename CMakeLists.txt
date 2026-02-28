cmake_minimum_required(VERSION 3.10)
project(lua_deobfuscator_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include_directories(src)

set(SOURCES
    src/lua_deobfuscator/Opcodes.cpp
    src/lua_deobfuscator/Parser.cpp
    src/lua_deobfuscator/Serializer.cpp
    src/lua_deobfuscator/Disassembler.cpp
    src/lua_deobfuscator/CFG.cpp
    src/lua_deobfuscator/Deobfuscator.cpp
    src/lua_deobfuscator/Assembler.cpp
)

add_executable(lua_deobfuscator_cpp src/main.cpp ${SOURCES})

# WebAssembly compilation with Emscripten
if(EMSCRIPTEN)
    set_target_properties(lua_deobfuscator_cpp PROPERTIES OUTPUT_NAME "lua_deobfuscator")
    set_target_properties(lua_deobfuscator_cpp PROPERTIES SUFFIX ".js")

    target_link_options(lua_deobfuscator_cpp PRIVATE
        "-s WASM=1"
        "-s ALLOW_MEMORY_GROWTH=1"
        "-s EXPORTED_RUNTIME_METHODS=['FS','ccall','cwrap']"
        "-s MODULARIZE=0"
        "-s SINGLE_FILE=0"
        "--bind"
    )
endif()
