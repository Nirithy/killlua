#ifndef LUA_OPCODES_H
#define LUA_OPCODES_H

#include <string>
#include <vector>
#include <map>
#include <optional>

namespace lua_deobfuscator {

enum class OpMode {
    iABC = 0,   // A:8, B:9, C:9
    iABx = 1,   // A:8, Bx:18
    iAsBx = 2,  // A:8, sBx:18 (signed)
    iAx = 3     // Ax:26
};

enum class OpArgMask {
    OpArgN = 0,  // argument is not used
    OpArgU = 1,  // argument is used
    OpArgR = 2,  // argument is a register or a jump offset
    OpArgK = 3   // argument is a constant or register/constant
};

enum class Opcode {
    MOVE = 0,
    LOADK = 1,
    LOADKX = 2,
    LOADBOOL = 3,
    LOADNIL = 4,
    GETUPVAL = 5,
    GETTABUP = 6,
    GETTABLE = 7,
    SETTABUP = 8,
    SETUPVAL = 9,
    SETTABLE = 10,
    NEWTABLE = 11,
    SELF = 12,
    ADD = 13,
    SUB = 14,
    MUL = 15,
    DIV = 16,
    MOD = 17,
    POW = 18,
    UNM = 19,
    NOT = 20,
    LEN = 21,
    CONCAT = 22,
    JMP = 23,
    EQ = 24,
    LT = 25,
    LE = 26,
    TEST = 27,
    TESTSET = 28,
    CALL = 29,
    TAILCALL = 30,
    RETURN = 31,
    FORLOOP = 32,
    FORPREP = 33,
    TFORCALL = 34,
    TFORLOOP = 35,
    SETLIST = 36,
    CLOSURE = 37,
    VARARG = 38,
    EXTRAARG = 39,
    IDIV = 40,
    BNOT = 41,
    BAND = 42,
    BOR = 43,
    BXOR = 44,
    SHL = 45,
    SHR = 46,
    GETFIELDU = 47,
    GETFIELDT = 48,
    CLASS = 49,
    OR = 59,
    AND = 60,
    NEQ = 61,
    GE = 62,
    GT = 63
};

struct OpcodeInfo {
    std::string name;
    OpMode mode;
    OpArgMask arg_b;
    OpArgMask arg_c;
    bool test_flag;
    bool set_a;
    std::string description;
};

const OpcodeInfo* get_opcode_info(Opcode opcode);
const OpcodeInfo* get_opcode_info(int opcode);
std::string get_opcode_name(Opcode opcode);
std::string get_opcode_name(int opcode);
OpMode get_opcode_mode(Opcode opcode);
OpMode get_opcode_mode(int opcode);
Opcode map_raw_opcode(int raw_op, int version);
int unmap_opcode(Opcode op, int version);

// Instruction field sizes and positions
constexpr int SIZE_OP = 6;
constexpr int SIZE_A = 8;
constexpr int SIZE_B = 9;
constexpr int SIZE_C = 9;
constexpr int SIZE_Bx = SIZE_B + SIZE_C;
constexpr int SIZE_Ax = SIZE_A + SIZE_B + SIZE_C;

constexpr int POS_OP = 0;
constexpr int POS_A = SIZE_OP;
constexpr int POS_C = POS_A + SIZE_A;
constexpr int POS_B = POS_C + SIZE_C;
constexpr int POS_Bx = POS_C;
constexpr int POS_Ax = POS_A;

constexpr int MASK_OP = (1 << SIZE_OP) - 1;
constexpr int MASK_A = (1 << SIZE_A) - 1;
constexpr int MASK_B = (1 << SIZE_B) - 1;
constexpr int MASK_C = (1 << SIZE_C) - 1;
constexpr int MASK_Bx = (1 << SIZE_Bx) - 1;
constexpr int MASK_Ax = (1 << SIZE_Ax) - 1;

constexpr int MAXARG_A = MASK_A;
constexpr int MAXARG_B = MASK_B;
constexpr int MAXARG_C = MASK_C;
constexpr int MAXARG_Bx = MASK_Bx;
constexpr int MAXARG_sBx = MAXARG_Bx >> 1;

constexpr int BITRK = 1 << (SIZE_B - 1);
constexpr int MAXINDEXRK = BITRK - 1;

inline bool ISK(int x) { return (x & BITRK) != 0; }
inline int INDEXK(int x) { return x & ~BITRK; }
inline int RKASK(int x) { return x | BITRK; }

} // namespace lua_deobfuscator

#endif // LUA_OPCODES_H
