// M6 — Remotion re-render (PLAN.md Section 5, M6.4).
//
// Renders a composition from your Remotion project with patched props:
//   npx remotion render <CompId> <out.mp4> --props=props_v2.json
//
// Usage:
//   node autofix/render.mjs --project C:\videogen\video --composition McdBusinessStory \
//       --out out\video_v2.mp4 --props props_v2.json [--frames 0-900]
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

function parseArgs(argv) {
  const a = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith("--")) a[argv[i].slice(2)] = argv[i + 1];
  }
  return a;
}

function main() {
  const { project, composition, out, props, frames } = parseArgs(process.argv.slice(2));
  if (!project || !composition || !out) {
    console.error("usage: node autofix/render.mjs --project <dir> --composition <id> --out <path> [--props <json>] [--frames a-b]");
    process.exit(1);
  }
  if (!existsSync(join(project, "package.json"))) {
    console.error(`[render] no package.json in ${project}`);
    process.exit(1);
  }
  const cmd = process.platform === "win32" ? "npx.cmd" : "npx";
  const args = ["remotion", "render", composition, out];
  if (props) args.push("--props", props);
  if (frames) args.push("--frames", frames);
  console.log(`[render] ${cmd} ${args.join(" ")}  (cwd=${project})`);
  const r = spawnSync(cmd, args, { cwd: project, encoding: "utf8", stdio: "inherit", shell: process.platform === "win32" });
  if (r.status !== 0) {
    console.error(`[render] failed with exit ${r.status}`);
    process.exit(r.status || 1);
  }
  console.log(`[render] done -> ${out}`);
}

if (process.argv[1] && process.argv[1].endsWith("render.mjs")) main();