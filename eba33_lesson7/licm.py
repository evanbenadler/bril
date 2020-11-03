import json
import sys

from form_blocks import form_blocks
import cfg
import ssa

def find_backedges(fn, succs, doms):
    backedges = []
    for a in succs:
        for b in succs[a]:
            if b in doms[a]:
                backedges.append((a,b))
    return backedges

""" very inefficient implementation, but simplicity
should rule this out as a source of bugs """
def form_natural_loop(preds, backedge):
    last_l = []
    l = [backedge[1]]
    def every_node_in_l(l, nodes):
        if len(nodes) == 0:
            return False
        for n in nodes:
            if n not in l:
                return False
        return True
    while last_l != l:
        last_l = l
        for v in preds:
            if every_node_in_l(l, preds[v]):
                l.append(v)
    return l

def get_loop_defs(blockmap, loop):
    defs = []
    for blockname in loop:
        for instr in blockmap[blockname]:
            if 'dest' in instr:
                defs.append(instr['dest'])
    return defs

""" could use an interval analysis to be agrressive with div """
def side_effect_free(instr):
    return instr['op'] not in ['print', 'call', 'div']

""" Returns a list of dests corresponding to loop invariant, side effect free
instructions from loop.
The list is such that the dependencies are in order. """
def get_loop_invariant_instrs(blockmap, loop):
    li = []
    last_li = [None]
    loop_defs = get_loop_defs(blockmap, loop)
    def args_are_loop_invariant(instr, li_defs, loop_defs):
        for arg in instr.get('args', []):
            if arg in loop_defs and arg not in li:
                return False
        return True
    while last_li != li:
        last_li = li
        for blockname in loop:
            block = blockmap[blockname]
            for instr in block:
                if 'dest' in instr and instr.get('op','')!='phi' and side_effect_free(
                        instr) and args_are_loop_invariant(instr, li, loop_defs):
                    li.append(instr['dest'])
    return li

""" Updates blockmap to remove instructions which define anything in li.
Returns a list of the instructions which need to be in the loop preheader.
This list preserves the ordering of li. """
def remove_li(blockmap, li):
    li_dict = {} # maps vars in li to instructions that define them
    for blockname in blockmap:
        new_instrs = []
        for i in blockmap[blockname]:
            if 'dest' in i and i['dest'] in li:
                li_dict[i['dest']] = i
            else:
                new_instrs.append(i)
        blockmap[blockname] = new_instrs
    return [li_dict[var] for var in li]

""" Returns a list of the labels which are in the loop and a list of labels
which are outside the loop. """
def split_phi_labels(labels, loop):
    return [l for l in labels if l in loop], [l for l in labels if l not in loop]

""" Returns either an id or phi instruction depending on length of labels/args
"""
def construct_id_or_phi(dest, typ, labels, args):
    if len(labels)==1:
        return {'dest':dest, 'type':typ, 'op':'id', 'args': args}
    else:
        return {'dest':dest, 'type':typ, 'op':'phi', 'args':args, 'labels':labels}

""" Split phi nodes from loop header into pre-header. Returns mapping from
variables to renamed preheader variable names. """
def split_phi(blockmap, loop, header, preheader):
    new_header_instrs = []
    new_preheader_instrs = []
    name_mapping = {}
    for h_instr in blockmap[header]:
        if h_instr.get('op','') != 'phi':
            new_header_instrs.append(h_instr)
        else:
            in_labels, out_labels = split_phi_labels(h_instr['labels'], loop)
            # if every label is in loop, keep phi unchanged in header
            if len(out_labels) == 0:
                new_header_instrs.append(h_instr)
            # if every label is outside loop, move phi unchanged to preheader
            elif len(in_labels) == 0:
                new_preheader_instrs.append(h_instr)
            # otherwise, split into two phi (or id) instructions
            else:
                new_dest = h_instr['dest']+'_LICM_PH'
                name_mapping[h_instr['dest']] = new_dest
                preheader_labels = []
                preheader_args = []
                header_labels = []
                header_args = []
                for index in range(len(h_instr['args'])):
                    if h_instr['labels'][index] in in_labels:
                        header_labels.append(h_instr['labels'][index])
                        header_args.append(h_instr['args'][index])
                    else:
                        preheader_labels.append(h_instr['labels'][index])
                        preheader_args.append(h_instr['args'][index])
                header_args.append(new_dest)
                header_labels.append(preheader)
                new_preheader_instrs.append(construct_id_or_phi(
                    new_dest, h_instr['type'], preheader_labels, preheader_args))
                new_header_instrs.append(construct_id_or_phi(
                    h_instr['dest'], h_instr['type'], header_labels, header_args))
    blockmap[header] = new_header_instrs
    blockmap[preheader] = new_preheader_instrs + blockmap[preheader]
    return name_mapping

""" If a loop invariant instruction uses a variable x defined by a phi
instruction in the header, but the phi was split, and there is a new variable
name defined by a new phi node in the preheader, then the uses are updated
accordingly """
def rename_preheader(name_mapping, blockmap, preheader):
    for instr in [i for i in blockmap[preheader] if 'args' in i and i.get('op','')!='phi']:
        instr['args'] = [name_mapping.get(a,a) for a in instr['args']]

def move_to_preheader(blockmap, loop_head, loop, li, preds, preheader_num):
    ph_blockname = 'PREHEADER_'+str(preheader_num)
    ph_instrs = remove_li(blockmap, li)
    ph_instrs.append({'op':'jmp', 'labels': [loop_head]})
    blockmap[ph_blockname] = ph_instrs
    for pred in [p for p in preds[loop_head] if p not in loop]:
        terminator = blockmap[pred][-1]
        terminator['labels'] = [ph_blockname if l==loop_head else l for
                l in terminator['labels']]
    rename_preheader(split_phi(blockmap, loop, loop_head, ph_blockname), blockmap, ph_blockname)

def blockmap2instrs(blockmap):
    instrs = []
    for blockname in blockmap:
        instrs.append({'label': blockname})
        instrs.extend(blockmap[blockname])
    return instrs

def loop2string(loop):
    return ','.join(loop)

def licm(fn):
    fn = ssa.to_ssa(fn)
    blockmap = cfg.block_map(form_blocks(fn['instrs']))
    cfg.add_terminators(blockmap)
    preds, succs = cfg.edges(blockmap)
    doms = ssa.find_dominators(fn)
    preheader_num = 0
    loops_seen = set()

    for backedge in find_backedges(fn, succs, doms):
        loop = form_natural_loop(preds, backedge)
        if loop2string(loop) in loops_seen:
            continue
        loops_seen.add(loop2string(loop))
        li = get_loop_invariant_instrs(blockmap, loop)
        if len(li) > 0:
            move_to_preheader(blockmap, backedge[1], loop, li, preds, preheader_num)
            preheader_num += 1

    fn['instrs'] = blockmap2instrs(blockmap)
    return ssa.from_ssa(fn) 
    
def licm_program(prog):
    new_prog = prog.copy()
    new_prog['functions'] = [licm(fn) for fn in prog['functions']]
    return new_prog

if __name__ == '__main__':
    prog = json.load(sys.stdin)
    new_prog = licm_program(prog)
    print(json.dumps(new_prog, indent=2, sort_keys=True))
