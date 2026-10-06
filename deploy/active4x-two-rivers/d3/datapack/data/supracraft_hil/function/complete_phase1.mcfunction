data modify storage supracraft:active4x hil.phase1_complete set value 1
say SUPRACRAFT_D3_PHASE1_COMPLETE
tellraw @a {"text":"SupraCraft HIL phase 1 complete. Disconnect now; the harness will restart the server and tell you when to reconnect.","color":"green"}
