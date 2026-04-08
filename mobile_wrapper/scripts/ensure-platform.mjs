import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

const platform = (process.argv[2] || "").trim().toLowerCase();

if (!["android", "ios"].includes(platform)) {
  console.error("Usage: node scripts/ensure-platform.mjs <android|ios>");
  process.exit(1);
}

const root = process.cwd();
const platformDir = path.join(root, platform);

function run(command) {
  execSync(command, { stdio: "inherit", cwd: root, env: process.env });
}

if (!existsSync(platformDir)) {
  run(`npx cap add ${platform}`);
}

run(`npx cap sync ${platform}`);
