import json
import sys
from functools import reduce

from form_blocks import form_blocks
import cfg

class VarRange:
    def __init__(self, lb, ub, bounds):
        self.lb = lb  # bool for "is lower bounded"
        self.ub = ub
        self.lower_bound = None
        self.upper_bound = None
        if lb and ub:
            self.lower_bound = bounds[0]
            self.upper_bound = bounds[1]
        elif lb:
            self.lower_bound = bounds[0]
        elif ub:
            self.upper_bound = bounds[0]
    def __str__(self):
        return "{}..{}".format(
            self.lower_bound if self.lb else "-INF",
            self.upper_bound if self.ub else "INF")
    def add(self, other):
        lb = self.lb and other.lb
        ub = self.ub and other.ub
        bounds = []
        if lb:
            bounds.append(self.lower_bound + other.lower_bound)
        if ub:
            bounds.append(self.upper_bound + other.upper_bound)
        return VarRange(lb, ub, bounds)
    def sub(self, other):
        lb = self.lb and other.ub
        ub = self.ub and other.lb
        bounds = []
        if lb:
            bounds.append(self.lower_bound - other.upper_bound)
        if ub:
            bounds.append(self.upper_bound - other.upper_bound)
        return VarRange(lb, ub, bounds)
    def mul(self, other):
        """
        Heuristic: if both inputs are completely bounded,
        choose the bound with greatest magnitude for each factor.
        Multiply those two absolute values, and that becomes upper bound.
        Lower bound becomes negative of upper bound.
        """
        lb = self.lb and other.lb and self.ub and other.ub
        ub = lb
        bounds = []
        if lb: # (and ub)
            slb = abs(self.lower_bound)
            sub = abs(self.upper_bound)
            olb = abs(other.lower_bound)
            oub = abs(other.upper_bound)
            m = max(slb, sub) * max(olb, oub)
            bounds = [-1*m, m]
        return VarRange(lb, ub, bounds)
    def div(self, other):
        """
        Heuristic: if both inputs are completely bounded,
        The upper bound becomes the bound of self with the
        greatest magnitude divided by the bound of other
        with the smallest magnitude.
        Lower bound becomes negative of upper bound.
        """
        lb = self.lb and other.lb and self.ub and other.ub
        ub = lb
        bounds = []
        if lb: # (and ub)
            slb = abs(self.lower_bound)
            sub = abs(self.upper_bound)
            olb = abs(other.lower_bound)
            oub = abs(other.upper_bound)
            m = (int)(max(slb, sub) / min(olb, oub))
            bounds = [-1*m, m]
        return VarRange(lb, ub, bounds)
    def widen(self, other):
        lb = self.lb and other.lb
        ub = self.ub and other.ub
        bounds = []
        if lb:
            bounds.append(min(self.lower_bound, other.lower_bound))
        if ub:
            bounds.append(max(self.upper_bound, other.upper_bound))
        return VarRange(lb, ub, bounds)

RANGE_UNKNOWN = VarRange(False,False,[])

def interval_meet(v1, v2):
    """ Step 1: If a variable is present in one
    but not the other, copy it and its range to
    the other dict.
    """
    t1 = v1.copy()
    t2 = v2.copy()
    for k,v in v1.items():
        if k not in v2:
            t2[k] = v
    for k,v in v2.items():
        if k not in v1:
            t1[k] = v
    """ Step 2: Set each variable's range to
    the "widening" of the two ranges
    """
    return {k: t1[k].widen(t2[k]) for k in t1}

def interval_transfer(b, in_):
    out = in_.copy()
    for instr in b:
        if 'dest' in instr and instr.get('type','')=='int':
            r = RANGE_UNKNOWN  # set r to this assignment's range
            if instr['op'] == 'const':
                r = VarRange(True, True, [instr['value'], instr['value']])
            elif instr['op'] == 'id':
                r = out.get(instr['args'][0], RANGE_UNKNOWN)
            elif instr['op'] == 'add':
                r = out.get(instr['args'][0], RANGE_UNKNOWN).add(
                    out.get(instr['args'][1], RANGE_UNKNOWN))
            elif instr['op'] == 'mul':
                r = out.get(instr['args'][0], RANGE_UNKNOWN).mul(
                    out.get(instr['args'][1], RANGE_UNKNOWN))
            elif instr['op'] == 'sub':
                r = out.get(instr['args'][0], RANGE_UNKNOWN).sub(
                    out.get(instr['args'][1], RANGE_UNKNOWN))
            elif instr['op'] == 'div':
                r = out.get(instr['args'][0], RANGE_UNKNOWN).div(
                    out.get(instr['args'][1], RANGE_UNKNOWN))

            if instr['dest'] in out:
                out[instr['dest']] = out[instr['dest']].widen(r)
            else:
                out[instr['dest']] = r
    return out

def stringify_var_mapping(m):
    return {v: str(m[v]) for v in m}

def stringify_interval_output(out):
    return {block_name: stringify_var_mapping(out[block_name]) for block_name in out}

def interval_analysis(instrs):
    blocks = form_blocks(instrs)
    blockmap = cfg.block_map(blocks)
    cfg.add_terminators(blockmap)
    preds, succs = cfg.edges(blockmap)
    
    init = {}  # mapping from variable names to VarRange

    # assuming first entry in blockmap is the entry block
    in_ = {}
    in_[list(blockmap.keys())[0]] = init
    out = {k: init for k in blockmap}
    worklist = set()
    for k in blockmap.keys():
        worklist.add(k)
    while worklist:
        b = worklist.pop()
        if preds[b]:
            in_[b] = reduce(interval_meet, [out[p] for p in preds[b]])
        else:
            in_[b] = init
        prev_out = out[b]
        out[b] = interval_transfer(blockmap[b], in_[b])
        if stringify_var_mapping(out[b]) != stringify_var_mapping(prev_out):  # hack for deep copying
            #if b == 'for.cond.5':
                #print(json.dumps(stringify_interval_output(out), indent=2, sort_keys=True))
            for s in succs[b]:
                worklist.add(s)
    return out

if __name__ == '__main__':
    prog = json.load(sys.stdin)
    result = {}
    for func in prog['functions']:
        result[func["name"]] = stringify_interval_output(
                interval_analysis(func["instrs"]))
    print(json.dumps(result, indent=2, sort_keys=True))
