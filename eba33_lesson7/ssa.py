import json
import sys
import re

from form_blocks import form_blocks
import cfg
from functools import reduce

SSA_DEFAULT = 'SSA_DEFAULT'
SSA_ENTRY = 'SSA_ENTRY'

def postorder_sort(block, succs, visited):
    visited.add(block)
    l = []
    for s in succs:
        if s not in visited:
            l.extend(postorder_sort(s, succs, visited))
    l.append(block)
    return l

def find_dominators(fn):
    blockmap = cfg.block_map(form_blocks(fn['instrs']))
    cfg.add_terminators(blockmap)
    preds, succs = cfg.edges(blockmap)

    entry = list(blockmap.keys())[0]
    sorted_blocks = postorder_sort(entry, succs, set())
    sorted_blocks.reverse()

    dom = {vertex: set(sorted_blocks) for vertex in sorted_blocks}
    dom[entry] = {entry}
    new_dom = dom.copy()
    while True:
        for vertex in sorted_blocks:
            temp = reduce(lambda s1, s2: s1 & s2, [new_dom[p] for p in ([vertex]+preds[vertex])])
            temp.add(vertex)
            new_dom[vertex] = temp.copy()
        if dom == new_dom:
            return dom
        else:
            dom = new_dom.copy()

def dom_tree(fn):
    dom = find_dominators(fn)
    blockmap = cfg.block_map(form_blocks(fn['instrs']))
    cfg.add_terminators(blockmap)

    def subtree(root):
        descendants = [b for b in dom.keys() if b!=root and root in dom[b]]
        children = []
        for d in descendants:
            is_child = True
            for dd in dom[d]:
                if d!=dd and dd in descendants:
                    is_child = False
                    break
            if is_child:
                children.append(d)
        tree = {}
        for c in children:
            tree[c] = subtree(c)
        return tree

    root = list(blockmap.keys())[0]
    return {root: subtree(root)}

def dom_tree_flat(fn):
    dom = find_dominators(fn)
    blockmap = cfg.block_map(form_blocks(fn['instrs']))
    cfg.add_terminators(blockmap)

    domtree = {}
    
    for root in blockmap:
        descendants = [b for b in dom.keys() if b!=root and root in dom[b]]
        children = []
        for d in descendants:
            is_child = True
            for dd in dom[d]:
                if d!=dd and dd in descendants:
                    is_child = False
                    break
            if is_child:
                children.append(d)
        domtree[root] = children
    return domtree

# return blocks not strictly dominated by a block, but predecessor is dominated
def dom_frontier(fn):
    dom = find_dominators(fn)
    blockmap = cfg.block_map(form_blocks(fn['instrs']))
    cfg.add_terminators(blockmap)
    preds, succs = cfg.edges(blockmap)
    
    frontier = {}
    for block in dom.keys():
        descendants_strict = [b for b in dom.keys() if block in dom[b] and block!=b]
        descendants = descendants_strict + [block]
        descendant_succs = set()
        for d in descendants:
            for s in succs[d]:
                descendant_succs.add(s)
        frontier[block] = [ds for ds in descendant_succs if ds not in descendants_strict]

    return frontier

def find_dominators_program(prog):
    for fn in prog['functions']:
        for block, doms in find_dominators(fn).items():
            print(block + ' --> ' + str(doms))

def dom_tree_program(prog):
    for fn in prog['functions']:
        print(json.dumps(dom_tree(fn), indent=4, sort_keys=True))

def dom_frontier_program(prog):
    for fn in prog['functions']:
        for block, frontier in dom_frontier(fn).items():
            print(block + ' --> ' + str(frontier))

def contains_phi(block, var):
    for phi in [i for i in block if i.get('op', '')=='phi']:
        if phi['dest'] == var:
            return True
    return False

def get_oldname(name):
    m = re.search(r'_SSA_', name)
    if m:
        return name[:m.start()]
    else:
        return name

# for debugging
def contains_op(blockmap, op):
    for b in blockmap.values():
        for i in b:
            if i.get('op', '') == op:
                print(i)
                return True
    return False

# adds labels to each block in blockmap
def add_labels(blockmap):
    for blockname, instr in blockmap.items():
        blockmap[blockname] = [{'label': blockname}] + instr

def to_ssa(fn):
    dom = find_dominators(fn)
    blockmap = cfg.block_map(form_blocks(fn['instrs']))
    cfg.add_terminators(blockmap)
    add_labels(blockmap)
    preds, succs = cfg.edges(blockmap)
    DF = dom_frontier(fn)
    domtree = dom_tree_flat(fn)
    entry = list(blockmap.keys())[0]
    
    # compute mapping from vars to basic blocks defining them
    # also, compute mapping from variables and function args to their types
    defs = {}
    types = {}
    for a in fn.get('args', []):
        types[a['name']] = a['type']
    for b in blockmap.keys():
        for instr in [i for i in blockmap[b] if 'dest' in i]:
            v = instr['dest']
            types[v] = instr['type']
            if v in defs:
                defs[v].add(b)
            else:
                defs[v] = {b}
    vars_and_args = list(defs.keys()) + [a['name'] for a in fn.get('args', [])]
    # step 1: basic phi insertion
    for v in defs.keys():
        deflist = list(defs[v])
        for d in deflist:
            for block in DF[d]:
                if not contains_phi(blockmap[block], v):
                    # put phi after the label
                    blockmap[block] = blockmap[block][0:1] + [{"op":"phi", "dest":v, "type": types[v],
                        "args":[], "labels":[]}] + blockmap[block][1:]
                defs[v].add(block)
                if block not in deflist:
                    deflist.append(block)
    # step 2: renaming
    stack = {v: [] for v in vars_and_args}
    freshnum = {v: 0 for v in vars_and_args} # helps generate fresh names
    def rename_var(oldname):
        newname = oldname + '_SSA_' + str(freshnum[oldname])
        freshnum[oldname] += 1
        stack[oldname].append(newname)
        return newname
    def rename(block):
        stacksize = {v: 0 for v in vars_and_args} # how many times we pushed to each stack
        for instr in blockmap[block]:
            if instr.get('op','')!='phi' and 'args' in instr:
                instr['args'] = [stack[arg][-1] for arg in instr['args']]
            if 'dest' in instr:
                stacksize[instr['dest']] += 1
                instr['dest'] = rename_var(instr['dest'])
        for s in succs[block]:
            for p in [i for i in blockmap[s] if i.get('op','')=='phi']:
                oldname = get_oldname(p['dest'])
                if stack[oldname]:
                    p['args'].append(stack[oldname][-1])
                    p['labels'].append(block)
        for b in domtree[block]:
            rename(b) 
        for v, size in stacksize.items():
            for _ in range(size):
                stack[v].pop()
    if 'args' in fn:
        fn['args'] = [{'name': rename_var(a['name']), 'type': a['type']} for a in fn['args']]
    rename(list(blockmap.keys())[0])

    # post-process to expand each phi for each predecessor
    # if the variable has same oldname as a function argument, use that function arg
    # otherwise, use a meaningless default variable
    for blockname, instrs in blockmap.items():
        for phi in [i for i in instrs if i.get('op','')=='phi']:
            default = SSA_DEFAULT
            phi_oldname = get_oldname(phi['dest'])
            for argname in [a['name'] for a in fn.get('args',[])]:
                if phi_oldname == get_oldname(argname):
                    default = argname
            for pred in [p for p in preds[blockname] if p not in phi['labels']]:
                phi['labels'].append(pred)
                phi['args'].append(default)
            if blockname == entry:
                phi['labels'].append(SSA_ENTRY)
                phi['args'].append(default)

    new_fn = fn.copy()
    new_fn['instrs'] =  [{'label': SSA_ENTRY},
            {'dest':SSA_DEFAULT,'type':'int','op':'const','value':'0'}
            ] + [i for block in blockmap.values() for i in block]
    return new_fn

def from_ssa(fn):
    blockmap = cfg.block_map(form_blocks(fn['instrs']))
    cfg.add_terminators(blockmap)
    add_labels(blockmap)

    # For each block, construct a mapping from predecessors to list of
    # instructions the predecessor needs to execute before entering the block.
    # Then, add to blockmap and adjust control flow
    block2pred2instrs = {b: {} for b in blockmap.keys()}

    for blockname, instrs in blockmap.items():
        for phi in [i for i in instrs if i.get('op', '')=='phi']:
            for pred, var in zip(phi['labels'], phi['args']):
                block2pred2instrs[blockname][pred] = block2pred2instrs[blockname].get(pred, []) + [
                        {'dest': phi['dest'], 'type': phi['type'],
                        'op':'id', 'args': [var]}]
    for blockname in block2pred2instrs:
        for pred, ins in block2pred2instrs[blockname].items():
            new_blockname = 'SSA_' + pred + '_' + blockname
            ins = [{'label': new_blockname}] + ins
            blockmap[new_blockname] = ins
            ins.append({'op':'jmp', 'labels': [blockname]})
            terminator = blockmap[pred][-1]
            terminator['labels'] = [new_blockname if l==blockname else l for
                    l in terminator['labels']]
        
    new_fn = fn.copy()
    new_fn['instrs'] =  [i for block in blockmap.values() for i in block if i.get('op', '')!='phi']
    return new_fn

def to_ssa_program(prog):
    new_prog = prog.copy()
    new_prog['functions'] = [to_ssa(fn) for fn in prog['functions']]
    print(json.dumps(new_prog, indent=2, sort_keys=True))

def from_ssa_program(prog):
    new_prog = prog.copy()
    new_prog['functions'] = [from_ssa(fn) for fn in prog['functions']]
    print(json.dumps(new_prog, indent=2, sort_keys=True))

if __name__ == '__main__':
    prog = json.load(sys.stdin)
    if sys.argv[1] == '--doms':
        find_dominators_program(prog)
    elif sys.argv[1] == '--domtree':
        dom_tree_program(prog)
    elif sys.argv[1] == '--domfrontier':
        dom_frontier_program(prog)
    elif sys.argv[1] == '--tossa':
        to_ssa_program(prog)
    elif sys.argv[1] == '--fromssa':
        from_ssa_program(prog)
    else:
        print('Invalid argument')

