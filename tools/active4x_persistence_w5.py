#!/usr/bin/env python3
"""Bounded persistence/CAS adapter for Two Rivers W5."""
from __future__ import annotations
import copy, hashlib, json
from typing import Any

def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

class RevisionStore:
    def __init__(self, initial: dict[str,Any]):
        self.revision=0; self.state=copy.deepcopy(initial); self.applied=set()
    def snapshot(self):
        return {"revision":self.revision,"state":copy.deepcopy(self.state),"digest":_digest(self.state),"applied":sorted(self.applied)}
    def commit(self, expected_revision:int, op_id:str, state:dict[str,Any]):
        if expected_revision != self.revision:
            return {"accepted":False,"reason":"stale_revision","revision":self.revision}
        if op_id in self.applied:
            return {"accepted":False,"reason":"duplicate_operation","revision":self.revision}
        self.state=copy.deepcopy(state); self.applied.add(op_id); self.revision+=1
        return {"accepted":True,"revision":self.revision,"digest":_digest(self.state)}
    @classmethod
    def restore(cls,snapshot):
        obj=cls(snapshot["state"]); obj.revision=int(snapshot["revision"]); obj.applied=set(snapshot.get("applied",[]))
        if _digest(obj.state)!=snapshot["digest"]: raise ValueError("snapshot digest mismatch")
        return obj
