import json
import sys

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
    def lb(self):
        return self.lower_bound if self.lb else "-INF"
    def ub(self):
        return self.upper_bound if self.ub else "INF"
    def widen(self, other):
        lb = self.lb and other.lb
        ub = self.ub and other.ub
        if lb:
            bounds.append(min(self.lower_bound, other.lower_bound))
        if ub:
            bounds.append(max(self.upper_bound, other.upper_bound))
        return VarRange(lb, ub, bounds)

def interval_meet(v1, v2):
    """ Step 1: If a variable is present in one
    but not the other, copy it and its range to
    the other dict.
    """
    t1 = v1.copy()
    t2 = v2.copy()
    for k,v in v1.iteritems():
        if k not in v2:
            t2[k] = v
    for k,v in v2.iteritems():
        if k not in v1:
            t1[k] = v
    """ Step 2: Set each variable's range to
    the "widening" of the two ranges
    """
    return {k: t1[k].widen(t2[k]) for k in t1}

def interval_transfer(b, in_):
    pass

def interval_analysis(instrs):
    blocks = form_blocks(instrs)
    blockmap = cfg.block_map(blocks)
    cfg.add_terminators(blockmap)
    preds, succs = cfg.edges(blockmap)
    
    init = {}  # mapping from variable names to VarRange

    # assuming first entry in blockmap is the entry block
    in_ = {}
    in_[blockmap.keys()[0]] = init
    out = {k: init for k in blockmap.keys()}
    worklist = set()
    for k in blockmap.keys():
        worklist.add(k)
    while worklist:
        b = worklist.pop()
        in_[b] = reduce(interval_meet, preds[b])
        prev_out = out[b]
        out[b] = transfer(b, in_[b])
        if out[b] != prev_out:
            for s in succs[b]:
                worklist.add(s)
    return out


if __name__ == '__main__':
    prog = json.load(sys.stdin)
    result = {}
    for func in prog['functions']:
        result[func["name"]] = interval_analysis(func["instrs"])
    print(json.dumps(func2ranges, indent=2, sort_keys=True))
