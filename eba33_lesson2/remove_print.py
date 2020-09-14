"""
This is a simple bril manipulation program created by eba33.  It simply outputs
the original program with all print calls removed.
"""

import json
import sys

def remove_prints():
    prog = json.load(sys.stdin)
    for func in prog['functions']:
        new_instrs = []
        for instr in func['instrs']:
            if instr.get('op', '') != 'print':
                new_instrs.append(instr)
        func['instrs'] = new_instrs
    print(json.dumps(prog, indent=2, sort_keys=True))

if __name__ == '__main__':
    remove_prints()
