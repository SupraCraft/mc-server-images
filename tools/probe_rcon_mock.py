#!/usr/bin/env python3
import json, socket, struct, subprocess, threading
seen=[]
def rx(c,n):
    out=b""
    while len(out)<n:
        x=c.recv(n-len(out))
        if not x: raise RuntimeError("closed")
        out+=x
    return out
def serve(s):
    c,_=s.accept()
    with c:
        while True:
            h=c.recv(4)
            if not h: return
            n=struct.unpack("<i",h)[0]; body=rx(c,n)
            rid,typ=struct.unpack("<ii",body[:8]); payload=body[8:-2].decode()
            seen.append([typ,payload])
            out=struct.pack("<ii",rid,0)+b"ok"+bytes(2)
            c.sendall(struct.pack("<i",len(out))+out)
s=socket.socket(); s.bind(("127.0.0.1",0)); s.listen()
threading.Thread(target=serve,args=(s,),daemon=True).start()
cmd=["python3","tools/minecraft_rcon_lifecycle.py","quiesce","--port",str(s.getsockname()[1]),"--password","fixture"]
p=subprocess.run(cmd,text=True,capture_output=True,check=True)
assert json.loads(p.stdout)["verb"]=="quiesce"
assert seen==[[3,"fixture"],[2,"save-all flush"],[2,"save-off"]],seen
print("PASS mock RCON auth and quiesce command order")
