import json
import sys

TERMINATORS = ['jmp', 'br', 'ret']
COMMUNATIVE = ['add', 'mul', 'eq', 'and', 'or']

def form_blocks(body):
    cur_block = []

    for instr in body:
        if 'op' in instr:
            cur_block.append(instr)
            if(instr['op'] in TERMINATORS):
                yield cur_block
                cur_block = []
        else: # label
            yield cur_block
            cur_block = [instr]
    yield cur_block

def trivial_dce(block):
    converged = False
    while not converged:
        last_def = {} # var -> instr index       defined once but not used yet
        indexes_to_delete = []
        for i, instr in enumerate(block):
            if 'args' in instr:
                for arg in instr['args']:
                    last_def.pop(arg, None)
            if 'dest' in instr:
                if instr['dest'] in last_def:
                    indexes_to_delete.append(last_def[instr['dest']])
                else:
                    last_def[instr['dest']] = i

        new_block = []
        for i, instr in enumerate(block):
            if i not in indexes_to_delete:
                new_block.append(instr)
        if len(new_block) == len(block):
            converged = True
        block = new_block
    return block

# use strings as values (they are hashable)
# use this on instructions with a destination
# (call, arithmetic, const, id, comparison, logic operations)
def instr_to_val(var2num, instr):
    val = instr['op'] + '|'
    val += '|'.join(instr.get('funcs', []))
    if instr['op'] == 'const': 
        val += str(instr['value'])
    else:
        modified_args = map(lambda a: str(var2num.get(a, a)), instr.get('args', []))
        if instr['op'] in COMMUNATIVE:
            val += '|'.join(sorted(modified_args))
        else:
            val += '|'.join(modified_args)
    return val

def dest_appears(block, dest):
    for instr in block:
        if instr.get('dest', '') == dest:
            return True
    return False

def lvn(block):
    new_block = []
    next_num = 0
    next_fresh_name = 0
    table = {} # value-strings --> (value-number, canonical-var)
    var2num = {} # environment
    num2val = {} # allows lookups by number
    for i, instr in enumerate(block):
        new_instr = instr.copy()

        if 'args' in instr:
            new_instr['args'] = map(lambda a: table[num2val[var2num[a]]][1] if a in var2num else a, instr['args'])

        if 'dest' in instr:
            value = instr_to_val(var2num, instr)
            if value in table:
                new_instr = {'dest': instr['dest'], 'type': instr['type'], 'op': 'id', 'args': [table[value][1]]}
                var2num[instr['dest']] = table[value][0]
            else:
                dest = instr['dest']
                if dest_appears(block[i+1:], dest):
                    dest = 'LVN_FRESH_NAME_' + str(next_fresh_name)
                    next_fresh_name += 1
                    new_instr['dest'] = dest
                table[value] = next_num, dest
                var2num[instr['dest']] = next_num
                num2val[next_num] = value
                next_num += 1

        new_block.append(new_instr)
    return new_block
            

if __name__ == '__main__':
    prog = json.load(sys.stdin)
    for func in prog['functions']:
        new_instrs = []
        for block in form_blocks(func['instrs']):
            new_instrs.extend(trivial_dce(lvn(block)))
        func['instrs'] = new_instrs

    print(json.dumps(prog, indent=2, sort_keys=True))
