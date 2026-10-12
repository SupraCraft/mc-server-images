"use strict";
// Disposable Mineflayer 26.3 login oracle. Same request/result for human, CI and agents.
// No auth tokens, secrets, online Microsoft identities or privileged in-game commands.
const mineflayer = require("mineflayer");
const port = Number(process.env.MC_FORWARD_PORT);
const username = process.env.MC_FORWARD_USERNAME || "SupraProbe263";
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error("invalid bounded MC_FORWARD_PORT");
}
const result = {
  schema: "supracraft.forwarding-client/1",
  requested_version: "26.3",
  username,
  spawned: false,
  protocol: null,
  kicked: null,
  ended: false,
  error: null,
  timed_out: false
};
let finished = false;
let bot;
function finish() {
  if (finished) return;
  finished = true;
  process.stdout.write(JSON.stringify(result) + "\n");
  try { bot?.quit("disposable RDTE completed"); } catch {}
  setTimeout(() => process.exit(0), 300);
}
try {
  bot = mineflayer.createBot({
    host: "127.0.0.1",
    port,
    username,
    auth: "offline",
    version: "26.3",
    hideErrors: true
  });
  bot.once("spawn", () => {
    result.spawned = true;
    result.protocol = Number(bot.protocolVersion);
    setTimeout(finish, 700);
  });
  bot.on("kicked", (reason) => {
    result.kicked = typeof reason === "string" ? reason.slice(0, 250) :
      JSON.stringify(reason).slice(0, 250);
    setTimeout(finish, 200);
  });
  bot.on("error", (error) => {
    result.error = String(error?.message || error).slice(0, 250);
  });
  bot.on("end", () => {
    result.ended = true;
    if (!result.spawned) setTimeout(finish, 200);
  });
} catch (error) {
  result.error = String(error?.message || error).slice(0, 250);
  finish();
}
setTimeout(() => {
  result.timed_out = true;
  finish();
}, 45000);
