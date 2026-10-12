#!/usr/bin/env node
// npm entry point: runs the Python CLI and gives a clear message if python3 is missing.
"use strict";
const { spawnSync } = require("child_process");
const path = require("path");

const script = path.join(__dirname, "claude-session-restorer");
const result = spawnSync("python3", [script, ...process.argv.slice(2)], { stdio: "inherit" });

if (result.error) {
  if (result.error.code === "ENOENT") {
    console.error(
      "claude-session-restorer needs Python 3 (3.8+).\n" +
        "On macOS run:  xcode-select --install   (or: brew install python)"
    );
    process.exit(127);
  }
  console.error(result.error.message);
  process.exit(1);
}
process.exit(result.status === null ? 1 : result.status);
