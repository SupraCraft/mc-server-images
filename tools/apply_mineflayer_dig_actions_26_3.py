#!/usr/bin/env python3
"""Pin Mineflayer's numeric digging actions to the Java 26.3 Action enum."""
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
translations = [
    ("status: 2, // finish digging", "status: 3, // finish digging"),
    ("status: 1, // cancel digging", "status: 2, // cancel digging"),
]
for old, new in translations:
    if s.count(old) == 1 and s.count(new) == 0:
        s = s.replace(old, new)
    elif s.count(old) == 0 and s.count(new) == 1:
        pass
    else:
        raise SystemExit("Exact pinned Mineflayer digging source mismatch: " + old)
if s.count("status: 0, // start digging") != 1:
    raise SystemExit("Mineflayer start action missing")
p.write_text(s, encoding="utf-8")
print("26.3 START=0 ABORT=2 STOP=3: PASS")
