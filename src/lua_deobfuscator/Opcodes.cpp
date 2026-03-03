#include "Opcodes.h"

namespace lua_deobfuscator {

static const std::map<Opcode, OpcodeInfo> OPCODE_INFO = {
    {Opcode::MOVE, {"MOVE", OpMode::iABC, OpArgMask::OpArgR, OpArgMask::OpArgN, false, true, "R(A) := R(B)"}},
    {Opcode::LOADK, {"LOADK", OpMode::iABx, OpArgMask::OpArgK, OpArgMask::OpArgN, false, true, "R(A) := K(Bx)"}},
    {Opcode::LOADKX, {"LOADKX", OpMode::iABx, OpArgMask::OpArgN, OpArgMask::OpArgN, false, true, "R(A) := K(extra arg)"}},
    {Opcode::LOADBOOL, {"LOADBOOL", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgU, false, true, "R(A) := (Bool)B; if (C) pc++"}},
    {Opcode::LOADNIL, {"LOADNIL", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgN, false, true, "R(A), ..., R(A+B) := nil"}},
    {Opcode::GETUPVAL, {"GETUPVAL", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgN, false, true, "R(A) := UpValue[B]"}},
    {Opcode::GETTABUP, {"GETTABUP", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgK, false, true, "R(A) := UpValue[B][RK(C)]"}},
    {Opcode::GETTABLE, {"GETTABLE", OpMode::iABC, OpArgMask::OpArgR, OpArgMask::OpArgK, false, true, "R(A) := R(B)[RK(C)]"}},
    {Opcode::SETTABUP, {"SETTABUP", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, false, "UpValue[A][RK(B)] := RK(C)"}},
    {Opcode::SETUPVAL, {"SETUPVAL", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgN, false, false, "UpValue[B] := R(A)"}},
    {Opcode::SETTABLE, {"SETTABLE", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, false, "R(A)[RK(B)] := RK(C)"}},
    {Opcode::NEWTABLE, {"NEWTABLE", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgU, false, true, "R(A) := {} (size B,C)"}},
    {Opcode::SELF, {"SELF", OpMode::iABC, OpArgMask::OpArgR, OpArgMask::OpArgK, false, true, "R(A+1) := R(B); R(A) := R(B)[RK(C)]"}},
    {Opcode::ADD, {"ADD", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "R(A) := RK(B) + RK(C)"}},
    {Opcode::SUB, {"SUB", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "R(A) := RK(B) - RK(C)"}},
    {Opcode::MUL, {"MUL", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "R(A) := RK(B) * RK(C)"}},
    {Opcode::DIV, {"DIV", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "R(A) := RK(B) / RK(C)"}},
    {Opcode::MOD, {"MOD", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "R(A) := RK(B) % RK(C)"}},
    {Opcode::POW, {"POW", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "R(A) := RK(B) ^ RK(C)"}},
    {Opcode::UNM, {"UNM", OpMode::iABC, OpArgMask::OpArgR, OpArgMask::OpArgN, false, true, "R(A) := -R(B)"}},
    {Opcode::NOT, {"NOT", OpMode::iABC, OpArgMask::OpArgR, OpArgMask::OpArgN, false, true, "R(A) := not R(B)"}},
    {Opcode::LEN, {"LEN", OpMode::iABC, OpArgMask::OpArgR, OpArgMask::OpArgN, false, true, "R(A) := length of R(B)"}},
    {Opcode::CONCAT, {"CONCAT", OpMode::iABC, OpArgMask::OpArgR, OpArgMask::OpArgR, false, true, "R(A) := R(B).. ... ..R(C)"}},
    {Opcode::JMP, {"JMP", OpMode::iAsBx, OpArgMask::OpArgR, OpArgMask::OpArgN, false, false, "pc += sBx; if (A) close upvalues >= R(A-1)"}},
    {Opcode::EQ, {"EQ", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, true, false, "if ((RK(B) == RK(C)) ~= A) then pc++"}},
    {Opcode::LT, {"LT", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, true, false, "if ((RK(B) < RK(C)) ~= A) then pc++"}},
    {Opcode::LE, {"LE", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, true, false, "if ((RK(B) <= RK(C)) ~= A) then pc++"}},
    {Opcode::TEST, {"TEST", OpMode::iABC, OpArgMask::OpArgN, OpArgMask::OpArgU, true, false, "if not (R(A) <=> C) then pc++"}},
    {Opcode::TESTSET, {"TESTSET", OpMode::iABC, OpArgMask::OpArgR, OpArgMask::OpArgU, true, true, "if (R(B) <=> C) then R(A) := R(B) else pc++"}},
    {Opcode::CALL, {"CALL", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgU, false, true, "R(A), ..., R(A+C-2) := R(A)(R(A+1), ..., R(A+B-1))"}},
    {Opcode::TAILCALL, {"TAILCALL", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgU, false, true, "return R(A)(R(A+1), ..., R(A+B-1))"}},
    {Opcode::RETURN, {"RETURN", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgN, false, false, "return R(A), ..., R(A+B-2)"}},
    {Opcode::FORLOOP, {"FORLOOP", OpMode::iAsBx, OpArgMask::OpArgR, OpArgMask::OpArgN, false, true, "R(A)+=R(A+2); if R(A) <?= R(A+1) then { pc+=sBx; R(A+3)=R(A) }"}},
    {Opcode::FORPREP, {"FORPREP", OpMode::iAsBx, OpArgMask::OpArgR, OpArgMask::OpArgN, false, true, "R(A)-=R(A+2); pc+=sBx"}},
    {Opcode::TFORCALL, {"TFORCALL", OpMode::iABC, OpArgMask::OpArgN, OpArgMask::OpArgU, false, false, "R(A+3), ..., R(A+2+C) := R(A)(R(A+1), R(A+2))"}},
    {Opcode::TFORLOOP, {"TFORLOOP", OpMode::iAsBx, OpArgMask::OpArgR, OpArgMask::OpArgN, false, true, "if R(A+1) ~= nil then { R(A)=R(A+1); pc += sBx }"}},
    {Opcode::SETLIST, {"SETLIST", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgU, false, false, "R(A)[(C-1)*FPF+i] := R(A+i), 1 <= i <= B"}},
    {Opcode::CLOSURE, {"CLOSURE", OpMode::iABx, OpArgMask::OpArgU, OpArgMask::OpArgN, false, true, "R(A) := closure(KPROTO[Bx])"}},
    {Opcode::VARARG, {"VARARG", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgN, false, true, "R(A), R(A+1), ..., R(A+B-2) = vararg"}},
    {Opcode::EXTRAARG, {"EXTRAARG", OpMode::iAx, OpArgMask::OpArgU, OpArgMask::OpArgU, false, false, "extra (larger) argument for previous opcode"}},
    {Opcode::IDIV, {"IDIV", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "R(A) := RK(B) // RK(C)"}},
    {Opcode::BNOT, {"BNOT", OpMode::iABC, OpArgMask::OpArgR, OpArgMask::OpArgN, false, true, "R(A) := ~R(B)"}},
    {Opcode::BAND, {"BAND", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "R(A) := RK(B) & RK(C)"}},
    {Opcode::BOR, {"BOR", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "R(A) := RK(B) | RK(C)"}},
    {Opcode::BXOR, {"BXOR", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "R(A) := RK(B) ~ RK(C)"}},
    {Opcode::SHL, {"SHL", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "R(A) := RK(B) << RK(C)"}},
    {Opcode::SHR, {"SHR", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "R(A) := RK(B) >> RK(C)"}},
    {Opcode::GETFIELDU, {"GETFIELDU", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgK, false, true, "R(A) := UpValue[B][RK(C)]"}},
    {Opcode::GETFIELDT, {"GETFIELDT", OpMode::iABC, OpArgMask::OpArgR, OpArgMask::OpArgK, false, true, "Custom GETFIELDT"}},
    {Opcode::CLASS, {"CLASS", OpMode::iABC, OpArgMask::OpArgU, OpArgMask::OpArgU, false, true, "Custom CLASS"}},
    {Opcode::OR, {"OR", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "Custom OR"}},
    {Opcode::AND, {"AND", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, false, true, "Custom AND"}},
    {Opcode::NEQ, {"NEQ", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, true, false, "Custom NEQ - if ((RK(B) ~= RK(C)) ~= A) then pc++"}},
    {Opcode::GE, {"GE", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, true, false, "Custom GE - if ((RK(B) >= RK(C)) ~= A) then pc++"}},
    {Opcode::GT, {"GT", OpMode::iABC, OpArgMask::OpArgK, OpArgMask::OpArgK, true, false, "Custom GT - if ((RK(B) > RK(C)) ~= A) then pc++"}},
};

const OpcodeInfo* get_opcode_info(Opcode opcode) {
    auto it = OPCODE_INFO.find(opcode);
    if (it != OPCODE_INFO.end()) {
        return &it->second;
    }
    return nullptr;
}

const OpcodeInfo* get_opcode_info(int opcode) {
    return get_opcode_info(static_cast<Opcode>(opcode));
}

std::string get_opcode_name(Opcode opcode) {
    const OpcodeInfo* info = get_opcode_info(opcode);
    if (info) {
        return info->name;
    }
    return "UNKNOWN_" + std::to_string(static_cast<int>(opcode));
}

std::string get_opcode_name(int opcode) {
    return get_opcode_name(static_cast<Opcode>(opcode));
}

OpMode get_opcode_mode(Opcode opcode) {
    const OpcodeInfo* info = get_opcode_info(opcode);
    if (info) {
        return info->mode;
    }
    return OpMode::iABC;
}

OpMode get_opcode_mode(int opcode) {
    return get_opcode_mode(static_cast<Opcode>(opcode));
}



Opcode map_raw_opcode(int raw_op, int version) {
    if (version == 0x53) {
        switch(raw_op) {
            case 0: return Opcode::MOVE;
            case 1: return Opcode::LOADK;
            case 2: return Opcode::LOADKX;
            case 3: return Opcode::LOADBOOL;
            case 4: return Opcode::LOADNIL;
            case 5: return Opcode::GETUPVAL;
            case 6: return Opcode::GETTABUP;
            case 7: return Opcode::GETTABLE;
            case 8: return Opcode::SETTABUP;
            case 9: return Opcode::SETUPVAL;
            case 10: return Opcode::SETTABLE;
            case 11: return Opcode::NEWTABLE;
            case 12: return Opcode::SELF;
            case 13: return Opcode::ADD;
            case 14: return Opcode::SUB;
            case 15: return Opcode::MUL;
            case 16: return Opcode::MOD;
            case 17: return Opcode::POW;
            case 18: return Opcode::DIV;
            case 19: return Opcode::IDIV;
            case 20: return Opcode::BAND;
            case 21: return Opcode::BOR;
            case 22: return Opcode::BXOR;
            case 23: return Opcode::SHL;
            case 24: return Opcode::SHR;
            case 25: return Opcode::UNM;
            case 26: return Opcode::BNOT;
            case 27: return Opcode::NOT;
            case 28: return Opcode::LEN;
            case 29: return Opcode::CONCAT;
            case 30: return Opcode::JMP;
            case 31: return Opcode::EQ;
            case 32: return Opcode::LT;
            case 33: return Opcode::LE;
            case 34: return Opcode::TEST;
            case 35: return Opcode::TESTSET;
            case 36: return Opcode::CALL;
            case 37: return Opcode::TAILCALL;
            case 38: return Opcode::RETURN;
            case 39: return Opcode::FORLOOP;
            case 40: return Opcode::FORPREP;
            case 41: return Opcode::TFORCALL;
            case 42: return Opcode::TFORLOOP;
            case 43: return Opcode::SETLIST;
            case 44: return Opcode::CLOSURE;
            case 45: return Opcode::VARARG;
            case 46: return Opcode::EXTRAARG;
            default: return Opcode::EXTRAARG;
        }
    }
    return static_cast<Opcode>(raw_op);
}

int unmap_opcode(Opcode op, int version) {
    if (version == 0x53) {
        switch(op) {
            case Opcode::MOVE: return 0;
            case Opcode::LOADK: return 1;
            case Opcode::LOADKX: return 2;
            case Opcode::LOADBOOL: return 3;
            case Opcode::LOADNIL: return 4;
            case Opcode::GETUPVAL: return 5;
            case Opcode::GETTABUP: return 6;
            case Opcode::GETTABLE: return 7;
            case Opcode::SETTABUP: return 8;
            case Opcode::SETUPVAL: return 9;
            case Opcode::SETTABLE: return 10;
            case Opcode::NEWTABLE: return 11;
            case Opcode::SELF: return 12;
            case Opcode::ADD: return 13;
            case Opcode::SUB: return 14;
            case Opcode::MUL: return 15;
            case Opcode::MOD: return 16;
            case Opcode::POW: return 17;
            case Opcode::DIV: return 18;
            case Opcode::IDIV: return 19;
            case Opcode::BAND: return 20;
            case Opcode::BOR: return 21;
            case Opcode::BXOR: return 22;
            case Opcode::SHL: return 23;
            case Opcode::SHR: return 24;
            case Opcode::UNM: return 25;
            case Opcode::BNOT: return 26;
            case Opcode::NOT: return 27;
            case Opcode::LEN: return 28;
            case Opcode::CONCAT: return 29;
            case Opcode::JMP: return 30;
            case Opcode::EQ: return 31;
            case Opcode::LT: return 32;
            case Opcode::LE: return 33;
            case Opcode::TEST: return 34;
            case Opcode::TESTSET: return 35;
            case Opcode::CALL: return 36;
            case Opcode::TAILCALL: return 37;
            case Opcode::RETURN: return 38;
            case Opcode::FORLOOP: return 39;
            case Opcode::FORPREP: return 40;
            case Opcode::TFORCALL: return 41;
            case Opcode::TFORLOOP: return 42;
            case Opcode::SETLIST: return 43;
            case Opcode::CLOSURE: return 44;
            case Opcode::VARARG: return 45;
            case Opcode::EXTRAARG: return 46;
            default: return 46;
        }
    }
    return static_cast<int>(op);
}
} // namespace lua_deobfuscator
