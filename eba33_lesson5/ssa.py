import json
import sys
import re

from form_blocks import form_blocks
import cfg
from functools import reduce

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

    sorted_blocks = postorder_sort(list(blockmap.keys())[0], succs, set())
    sorted_blocks.reverse()

    dom = {}
    new_dom = {}
    while True:
        for vertex in sorted_blocks:
            pred_doms = [new_dom[p].copy() for p in list(filter(lambda x: x in new_dom, preds[vertex]))]
            temp = reduce(lambda s1, s2: s1 & s2, (pred_doms if pred_doms else [set()]))
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

def dom_frontier(fn):
    dom = find_dominators(fn)
    blockmap = cfg.block_map(form_blocks(fn['instrs']))
    cfg.add_terminators(blockmap)
    preds, succs = cfg.edges(blockmap)
    
    frontier = {}
    for block in dom.keys():
        descendants = [b for b in dom.keys() if block in dom[b]]
        descendant_succs = set()
        for d in descendants:
            for s in succs[d]:
                descendant_succs.add(s)
        f = [ds for ds in descendant_succs if ds not in descendants]
        frontier[block] = f

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

def to_ssa(fn):
    dom = find_dominators(fn)
    blockmap = cfg.block_map(form_blocks(fn['instrs']))
    cfg.add_terminators(blockmap)
    preds, succs = cfg.edges(blockmap)
    DF = dom_frontier(fn)
    domtree = dom_tree_flat(fn)
    
    # compute mapping from vars to basic blocks defining them
    # also, compute a mapping from variables to their types
    defs = {}
    types = {}
    for b in blockmap.keys():
        for instr in [i for i in blockmap[b] if 'dest' in i]:
            v = instr['dest']
            types[v] = instr['type']
            if v in defs:
                defs[v].add(b)
            else:
                defs[v] = {b}

    # step 1: basic phi insertion
    for v in defs.keys():
        deflist = list(defs[v])
        for d in deflist:
            for block in DF[d]:
                if not contains_phi(blockmap[block], v):
                    blockmap[block] = [{"op":"phi", "dest":v, "type": types[v],
                        "args":[], "labels":[]}] + blockmap[block]
                defs[v].add(block)
                deflist.append(block)

    # step 2: renaming
    stack = {v: [] for v in defs.keys()}
    freshnum = {v: 0 for v in defs.keys()} # helps generate fresh names
    def rename(block):
        stacksize = {v: 0 for v in defs.keys()} # how many times we pushed to each stack
        for instr in blockmap[block]:
            if instr.get('op','')!='phi' and 'args' in instr:
                instr['args'] = [stack[arg][-1] for arg in instr['args']]
            if 'dest' in instr:
                oldname = instr['dest']
                newname = oldname + '_SSA_' + str(freshnum[oldname])
                freshnum[oldname] += 1
                instr['dest'] = newname
                stack[oldname].append(newname)
                stacksize[oldname] += 1
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
    rename(list(blockmap.keys())[0])
    new_fn = fn.copy()
    new_fn['intrs'] = [i for block in blockmap.values() for i in block]
    return new_fn
    
def to_ssa_program(prog):
    new_prog = prog.copy()
    new_prog['functions'] = [to_ssa(fn) for fn in prog['functions']]
    print(json.dumps(new_prog, indent=2, sort_keys=True))

def from_ssa(program):
    pass

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

