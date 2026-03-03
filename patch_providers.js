const fs = require('fs');

let html = fs.readFileSync('web/index.html', 'utf8');

const providersCode = `            monaco.languages.registerHoverProvider('lasm', {
                provideHover: function (model, position) {
                    const word = model.getWordAtPosition(position);
                    if (!word) return null;

                    const hoverData = {
                        'MOVE': 'MOVE A B \\n R(A) := R(B)',
                        'LOADK': 'LOADK A Bx \\n R(A) := Kst(Bx)',
                        'LOADKX': 'LOADKX A \\n R(A) := Kst(extra arg)',
                        'LOADBOOL': 'LOADBOOL A B C \\n R(A) := (Bool)B; if (C) pc++',
                        'LOADNIL': 'LOADNIL A B \\n R(A), R(A+1), ..., R(A+B) := nil',
                        'GETUPVAL': 'GETUPVAL A B \\n R(A) := UpValue[B]',
                        'GETTABUP': 'GETTABUP A B C \\n R(A) := UpValue[B][RK(C)]',
                        'GETTABLE': 'GETTABLE A B C \\n R(A) := R(B)[RK(C)]',
                        'SETTABUP': 'SETTABUP A B C \\n UpValue[A][RK(B)] := RK(C)',
                        'SETUPVAL': 'SETUPVAL A B \\n UpValue[B] := R(A)',
                        'SETTABLE': 'SETTABLE A B C \\n R(A)[RK(B)] := RK(C)',
                        'NEWTABLE': 'NEWTABLE A B C \\n R(A) := {} (size = B,C)',
                        'SELF': 'SELF A B C \\n R(A+1) := R(B); R(A) := R(B)[RK(C)]',
                        'ADD': 'ADD A B C \\n R(A) := RK(B) + RK(C)',
                        'SUB': 'SUB A B C \\n R(A) := RK(B) - RK(C)',
                        'MUL': 'MUL A B C \\n R(A) := RK(B) * RK(C)',
                        'MOD': 'MOD A B C \\n R(A) := RK(B) % RK(C)',
                        'POW': 'POW A B C \\n R(A) := RK(B) ^ RK(C)',
                        'DIV': 'DIV A B C \\n R(A) := RK(B) / RK(C)',
                        'IDIV': 'IDIV A B C \\n R(A) := RK(B) // RK(C)',
                        'BAND': 'BAND A B C \\n R(A) := RK(B) & RK(C)',
                        'BOR': 'BOR A B C \\n R(A) := RK(B) | RK(C)',
                        'BXOR': 'BXOR A B C \\n R(A) := RK(B) ~ RK(C)',
                        'SHL': 'SHL A B C \\n R(A) := RK(B) << RK(C)',
                        'SHR': 'SHR A B C \\n R(A) := RK(B) >> RK(C)',
                        'UNM': 'UNM A B \\n R(A) := -R(B)',
                        'BNOT': 'BNOT A B \\n R(A) := ~R(B)',
                        'NOT': 'NOT A B \\n R(A) := not R(B)',
                        'LEN': 'LEN A B \\n R(A) := length of R(B)',
                        'CONCAT': 'CONCAT A B C \\n R(A) := R(B).. ... ..R(C)',
                        'JMP': 'JMP A sBx \\n pc+=sBx; if (A) close all upvalues >= R(A - 1)',
                        'EQ': 'EQ A B C \\n if ((RK(B) == RK(C)) ~= A) then pc++',
                        'LT': 'LT A B C \\n if ((RK(B) <  RK(C)) ~= A) then pc++',
                        'LE': 'LE A B C \\n if ((RK(B) <= RK(C)) ~= A) then pc++',
                        'TEST': 'TEST A C \\n if not (R(A) <=> C) then pc++',
                        'TESTSET': 'TESTSET A B C \\n if (R(B) <=> C) then R(A) := R(B) else pc++',
                        'CALL': 'CALL A B C \\n R(A), ... ,R(A+C-2) := R(A)(R(A+1), ... ,R(A+B-1))',
                        'TAILCALL': 'TAILCALL A B C \\n return R(A)(R(A+1), ... ,R(A+B-1))',
                        'RETURN': 'RETURN A B \\n return R(A), ... ,R(A+B-2)',
                        'FORLOOP': 'FORLOOP A sBx \\n R(A)+=R(A+2); if R(A) <?= R(A+1) then { pc+=sBx; R(A+3)=R(A) }',
                        'FORPREP': 'FORPREP A sBx \\n R(A)-=R(A+2); pc+=sBx',
                        'TFORCALL': 'TFORCALL A C \\n R(A+3), ... ,R(A+2+C) := R(A)(R(A+1), R(A+2));',
                        'TFORLOOP': 'TFORLOOP A sBx \\n if R(A+1) ~= nil then { R(A)=R(A+1); pc += sBx }',
                        'SETLIST': 'SETLIST A B C \\n R(A)[(C-1)*FPF+i] := R(A+i), 1 <= i <= B',
                        'CLOSURE': 'CLOSURE A Bx \\n R(A) := closure(KPROTO[Bx])',
                        'VARARG': 'VARARG A B \\n R(A), R(A+1), ..., R(A+B-2) = vararg',
                        'EXTRAARG': 'EXTRAARG Ax \\n extra (larger) argument for previous opcode'
                    };

                    const op = word.word.toUpperCase();
                    if (hoverData[op]) {
                        return {
                            range: new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn),
                            contents: [
                                { value: '**' + op + '**' },
                                { value: hoverData[op] }
                            ]
                        };
                    }
                    return null;
                }
            });

            monaco.languages.registerCompletionItemProvider('lasm', {
                provideCompletionItems: function (model, position) {
                    const suggestions = [
                        'MOVE', 'LOADK', 'LOADKX', 'LOADBOOL', 'LOADNIL', 'GETUPVAL', 'GETTABUP', 'GETTABLE',
                        'SETTABUP', 'SETUPVAL', 'SETTABLE', 'NEWTABLE', 'SELF', 'ADD', 'SUB', 'MUL', 'MOD',
                        'POW', 'DIV', 'IDIV', 'BAND', 'BOR', 'BXOR', 'SHL', 'SHR', 'UNM', 'BNOT', 'NOT',
                        'LEN', 'CONCAT', 'JMP', 'EQ', 'LT', 'LE', 'TEST', 'TESTSET', 'CALL', 'TAILCALL',
                        'RETURN', 'FORLOOP', 'FORPREP', 'TFORCALL', 'TFORLOOP', 'SETLIST', 'CLOSURE', 'VARARG', 'EXTRAARG'
                    ].map(op => ({
                        label: op,
                        kind: monaco.languages.CompletionItemKind.Keyword,
                        insertText: op,
                        detail: 'Lua 5.3 Opcode'
                    }));

                    return { suggestions: suggestions };
                }
            });
`;

html = html.replace(
    /monaco\.editor\.defineTheme\('lasm-dark', \{/,
    providersCode + '\n            monaco.editor.defineTheme(\'lasm-dark\', {'
);

fs.writeFileSync('web/index.html', html);
