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

} // namespace lua_deobfuscator
