#!/usr/bin/env node
// npm entry point for both commands: runs the Python CLI with the same name and gives a clear
// message when python3 is missing.
"use strict";
const { spawnSync } = require("child_process");
const path = require("path");

const invoked = path.basename(process.argv[1] || "");
const name = invoked === "claude-session-restorer" ? "claude-session-restorer" : "claude-relay";
const script = path.join(__dirname, name);
const result = spawnSync("python3", [script, ...process.argv.slice(2)], { stdio: "inherit" });

if (result.error) {
  if (result.error.code === "ENOENT") {
    console.error(
      "claude-relay needs Python 3 (3.8+).\n" +
        "macOS: xcode-select --install   (or: brew install python)\n" +
        "Linux: install python3 with your package manager"
    );
    process.exit(127);
  }
  console.error(result.error.message);
  process.exit(1);
}
if (result.signal) {
  process.kill(process.pid, result.signal);
}
process.exit(result.status === null ? 1 : result.status);
