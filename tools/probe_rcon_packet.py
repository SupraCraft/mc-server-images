#!/usr/bin/env python3
import importlib.util, pathlib
p=pathlib.Path("tools/minecraft_rcon_lifecycle.py")
s=importlib.util.spec_from_file_location("r",p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
assert m.packet(7,2,"save-on")[4:12] == __import__("struct").pack("<ii",7,2)
assert m.packet(7,2,"save-on").endswith(b"save-on\0\0")
print("PASS RCON packet framing")
