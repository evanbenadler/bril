-Include copy propagation and tdce in to_ssa
-static and dynamic num instructions

I adjusted the provided LICM algorithm to work with SSA, which mostly
simplified it. I mark an instruction loop-invariant if every operand is either
defined outside the loop or defined by a loop invariant instruction. I move all
loop invariant instructions which don't (conservatively) contain side effects.



Adding a preheader block required fiddling with the phi nodes.

In the following program snippet:

.preheader
.header
  x5 = phi x1 x2 x3 x4 pred1 pred2 pred3 pred4

we have to do something depending on if pred1 ... pred4 are inside the loop or not.
Suppose pred1 and pred3 are inside the loop and pred2 and pred4 are outside.

Then we need to have the following:

.preheader
  x5_licm_preheader = phi x2 x4 pred2 pred4
.header
  x5 = phi x1 x3 x5_licm_preheader pred1 pred3 preheader

(If any of these phi nodes would just have one option, I create it using id.)



WHAT ABOUT LOOP INVARIANT INSTRUCTIONS WHICH DEPEND ON A MODIFIED PHI NODE??
