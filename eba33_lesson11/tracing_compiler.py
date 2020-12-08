import json
import sys
import re
import hashlib
import os

SPECULATIVE_LABEL = "SPECULATIVE"


def rename_instr(i, old_label, new_label):
    def rename_label(l):
        if l == old_label:
            return new_label
        else:
            return l
    if 'labels' in i:
        j = i
        j['labels'] = [rename_label(l) for l in i['labels']]
        return j
    else:
        return i

def branch2guard(branch, label, guard_target):
    true_label = branch['labels'][0]
    false_label = branch['labels'][1]
    if label == true_label:
        negation_var = 'GUARD_NEGATION_' + branch['args'][0]
        return [
        {'dest': negation_var, 'type': 'bool',
            'op': 'not', 'args': branch['args']},
        {'op': 'guard', 'args': [negation_var], 'labels': [guard_target]}
        ]
    else:
        return [{'op': 'guard', 'args': branch['args'], 'labels': [guard_target]}]

""" Takes the hot trace path and returns a new basic block for it. """
def gen_speculative_block(prog, path, guard_target):
    block = []
    block.append({'label': SPECULATIVE_LABEL})
    block.append({'op': 'speculate'})
    prints = []
    callstack = []
    arg2guard = {}
    labels = []

    # for i in range(len(path)):
        # if path[i][2].get('op', '') == 'br':
            # arg2guard[path[i][2]['args'][0]] = branch2guard(path[i][2], path[i+1][0], guard_target)

    for path_idx, i in enumerate(path):
        instr = i[2]
        if instr == {}:
            labels.append(i[0])
            continue
        
        if instr['op'] == 'jmp':
            pass
        elif instr['op'] == 'call' and 'dest' in instr:
            callstack.append((instr['dest'], instr['type']))
            fn_name = instr['funcs'][0]
            fn = [f for f in prog['functions'] if f['name'] == fn_name][0]
            for idx in range(len(instr.get('args', []))):
                block.append({'dest': fn['args'][idx]['name'],
                    'type': fn['args'][idx]['type'],
                    'op': 'id', 'args': [instr['args'][idx]]})
        elif instr['op'] == 'call':
            pass
        elif instr['op'] == 'ret' and 'args' in instr:
            c = callstack.pop()
            block.append({'dest': c[0], 'type': c[1], 'op': 'id', 'args': instr['args']})
        elif instr['op'] == 'ret':
            pass
        elif instr['op'] == 'print':
            prints.append(instr)
        elif instr['op'] == 'br':
            block.extend(branch2guard(instr, path[path_idx+1], guard_target))
        else:
            block.append(instr)
        
        """ Regardless of the instruction type, do a guard lookup """
        # if 'dest' in instr and instr['dest'] in arg2guard:
            # block.extend(arg2guard[instr['dest']])

    block.append({'op': 'commit'})
    block.extend(prints)
    block.append({'op': 'jmp', 'labels': [SPECULATIVE_LABEL]})

    # for l in labels:
        # block = [rename_instr(i, l, SPECULATIVE_LABEL) if i.get('op', '')=='phi' else i for i in block]

    return block
    

""" Takes the trace of the whole program and extracts *one*
subtrace which is repeated twice in a row. This
corresponds to a hot loop.
Returns None if nothing matches criteria """
def extract_hot_trace(trace):
    for i in range(len(trace)):
        # find next occurance
        for j in range(i+1, len(trace)):
            if trace[i] == trace[j]:
                # iterate until next occurance and check equality
                full_match = True
                for k in range(1, j-i):
                    if trace[i+k] != trace[j+k]:
                        full_match = False
                        break
                if full_match:
                    return trace[i:j]
    return None

def process_trace(tracedata):
    trace = []
    for line in tracedata:
        tokens = line.split(' ')
        trace.append((tokens[0], int(tokens[1]), (json.loads(tokens[2]))))
    return trace

""" Makes sure there is no fall through to the un-speculative path """
def fix_fallthrough(fn, label):
    for i in range(len(fn['instrs'])):
        if fn['instrs'][i].get('label', '') == label:
            op = fn['instrs'][i-1].get('op', '')
            if op != 'br' and op != 'jmp':
                fn['instrs'].insert(i, {'op': 'jmp', 'labels': [label]})

if __name__ == '__main__':
    prog = json.load(sys.stdin)
    with open('/tmp/briltrace', 'r') as briltrace:
        trace = process_trace(briltrace.readlines())
    path = extract_hot_trace(trace)
    if(path):
        block = gen_speculative_block(prog, path, path[0][0])
        fn = [f for f in prog['functions'] if f['name']==path[1][0]][0]
        fix_fallthrough(fn, path[0][0])
        fn['instrs'] = [rename_instr(i, path[0][0], SPECULATIVE_LABEL) for i in fn['instrs']]
        fn['instrs'].append({'op': 'ret'})
        fn['instrs'].extend(block)
    print(json.dumps(prog, indent=2, sort_keys=True))
