## Commands

`bril2json < benchmarks/euclid.bril | brili -t`

`bril2json < benchmarks/euclid.bril | python
eba33_lesson11/tracing_compiler.py`

## Design Decisions

I extracted a hot path by considering each instruction, from the beginning to
the end of the trace, and seeing if it was the beginning of two identical
back-to-back subtraces. This methods seems to find decent candidates for hot
loops.

I first attempted this in SSA form, since prints could be delayed after the
commit with no worry of clobbering, and since guards could be moved to the
definitions of the variables they require. However, I started getting PTSD with
stitching the phi nodes back together, so I decided to use a non-SSA format
instead. This also helped debuggability. 

I create a new speculative basic block, which runs the straightline code and
guards. The guards point back to the block which the speculative one replaces.
The bottom of the speculative basic block loops back to the top.

I had to do some basic inlining stuff with calls and returns, I ignored jumps
entirely, and I converted branches into guards, sometimes needing to negate the
variable first.

For the tracing, I modified brili.ts to print instructions and labels.

## Evaluation

This project is incomplete. Brench was not set up, since I wasn't sure about
how the profiler and compiler could agree on the same filename for the trace
data. I tried envioronment variables and even hashing the standard input, which
should be the same, but I didn't get these methods working. As a consequence, I
only tested on benchmarks without arguments, since I usually rely on brench to
get that to work.

For Sqrt and Euclid, correctness is preserved in both cases. However, Sqrt uses
many more dynamic instructions with the supposed optimization, and Euclid uses
far too few, indicating there may be a correctness issue there.

This assignment had some surprising challenges, mostly phi node related, but
unfortunately the bottom line here is that I ran out of time.
