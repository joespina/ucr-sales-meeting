#!/usr/bin/env python3
"""Print the MEETINGS object from index.html as runnable JS (`var MEETINGS = {...};`).

Used by validate.sh. Brace-counts with string awareness rather than regexing, because
listing notes contain braces and apostrophes that break naive patterns.
"""
import sys

def extract(html="index.html"):
    s = open(html, encoding="utf-8").read()
    i = s.index("const MEETINGS = {")
    j = s.index("{", i)
    depth, k, instr, esc = 0, j, None, False
    while k < len(s):
        c = s[k]
        if instr:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == instr: instr = None
        else:
            if c in "\"'": instr = c
            elif c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0: break
        k += 1
    return s[j:k + 1]

if __name__ == "__main__":
    print("var MEETINGS = " + extract(sys.argv[1] if len(sys.argv) > 1 else "index.html") + ";")
