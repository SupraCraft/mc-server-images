data modify storage supracraft:active4x staging_pack set value {loaded:1,version:"d2a"}
execute unless data storage supracraft:active4x d2b_fixture run schedule function supracraft:active4x/setup_d2b_fixture 20t replace
say SUPRACRAFT_D2A_DATAPACK_LOADED
