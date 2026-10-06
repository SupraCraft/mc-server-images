#!/usr/bin/env python3
import argparse, json, socket, struct

def recv_exact(s,n):
    out=b""
    while len(out)<n:
        chunk=s.recv(n-len(out))
        if not chunk: raise RuntimeError("RCON connection closed")
        out+=chunk
    return out

def packet(req_id,typ,payload):
    body=struct.pack("<ii",req_id,typ)+payload.encode()+b"\0\0"
    return struct.pack("<i",len(body))+body

def exchange(s,req_id,typ,payload):
    s.sendall(packet(req_id,typ,payload))
    size=struct.unpack("<i",recv_exact(s,4))[0]
    body=recv_exact(s,size)
    rid,rtyp=struct.unpack("<ii",body[:8])
    return rid,rtyp,body[8:-2].decode(errors="replace")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("verb",choices=["quiesce","resume","health"])
    p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",type=int,default=25575)
    p.add_argument("--password",required=True)
    a=p.parse_args()
    with socket.create_connection((a.host,a.port),timeout=5) as s:
        rid,_,_=exchange(s,1,3,a.password)
        if rid == -1: raise SystemExit("RCON authentication failed")
        cmds={"quiesce":["save-all flush","save-off"],"resume":["save-on"],"health":["list"]}[a.verb]
        replies=[]
        for i,cmd in enumerate(cmds,2):
            rr,_,msg=exchange(s,i,2,cmd)
            if rr != i: raise SystemExit("RCON response id mismatch")
            replies.append({"command":cmd,"response":msg})
    print(json.dumps({"schema":"minecraft-world-lifecycle-receipt/1","verb":a.verb,"replies":replies},sort_keys=True))
if __name__=="__main__": main()
