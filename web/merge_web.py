import base64
import os
import re

def merge():
    template_path = 'web/index.html'
    js_path = 'build_wasm/lua_deobfuscator.js'
    wasm_path = 'build_wasm/lua_deobfuscator.wasm'
    output_path = 'web/lua_deobfuscator_web.html'

    if not all(os.path.exists(p) for p in [template_path, js_path, wasm_path]):
        print("Missing required files for merging.")
        return

    with open(template_path, 'r') as f:
        html = f.read()

    with open(js_path, 'r') as f:
        js_content = f.read()

    with open(wasm_path, 'rb') as f:
        wasm_base64 = base64.b64encode(f.read()).decode('utf-8')

    wasm_inline = f'var wasmBinary = Uint8Array.from(atob("{wasm_base64}"), c => c.charCodeAt(0));\n'
    # For non-MODULARIZE, Module is global. We need to set wasmBinary on it before the script runs.
    module_init = "var Module = { wasmBinary: wasmBinary };\n"

    js_final = f'<script>\n{wasm_inline}{module_init}{js_content}\n</script>'

    final_html = html.replace('<!-- INSERT_JS_HERE -->', js_final)

    with open(output_path, 'w') as f:
        f.write(final_html)

    print(f"Successfully merged into {output_path}")

if __name__ == '__main__':
    merge()
