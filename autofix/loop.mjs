// M6 — iterate-to-80 loop (PLAN.md Section 5, M6.5).
//
//   render -> score -> patch props + rewrite -> re-render -> rescore
//   until score >= pass.overall_min or max 3 iterations.
//
// Usage:
//   node autofix/loop.mjs --project C:\videogen\video --composition McdBusinessStory \
//       --video out\video.mp4 --props src\mcd\data\businessStory.json \
//       [--title "Candidate Title"] [--max-iterations 3] [--dry]
import { existsSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { scoreVideo, readJson, ROOT } from "./lib.mjs";
import { patchProps } from "./patch-props.mjs";
import { rewriteScript } from "./rewrite.mjs";
import { spawnSync } from "node:child_process";

function parseArgs(argv) {
  const a = { maxIterations: 3 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i].replace(/^--/, "");
    if (k === "dry") { a.dry = true; continue; }
    if (k === "max-iterations") a.maxIterations = parseInt(argv[++i], 10);
    else if (argv[i].startsWith("--")) a[k] = argv[++i];
  }
  return a;
}

async function main() {
  const { project, composition, video, props, title, maxIterations, dry } = parseArgs(process.argv.slice(2));
  if (!project || !composition || !video) {
    console.error("usage: node autofix/loop.mjs --project <dir> --composition <id> --video <mp4> [--props <json>] [--title T] [--dry]");
    process.exit(1);
  }
  const python = process.platform === "win32" ? join(ROOT, ".venv", "Scripts", "python.exe") : "python";

  let scorecard = scoreVideo(video, title, python);
  console.log(`[loop] iteration 0: ${scorecard.verdict} ${scorecard.score}/100`);
  for (let it = 1; it <= maxIterations; it++) {
    const passCfg = { overall_min: 80 };
    if (scorecard.score >= passCfg.overall_min) {
      console.log(`[loop] PASSED at ${scorecard.score}/100 — stopping`);
      break;
    }
    if (dry) {
      console.log(`[loop] dry run: would patch iteration ${it} (score ${scorecard.score}); skipping render`);
      scorecard.score = scorecard.score + 15; // simulate improvement for demo
      continue;
    }
    const propsPath = props || join(project, "props.json");
    if (!existsSync(propsPath)) {
      console.error(`[loop] no props file at ${propsPath} — cannot auto-patch; manual fix required`);
      break;
    }
    const s = readJson(propsPath);
    const { patched } = patchProps(s, scorecard);
    const changed = await rewriteScript(s, scorecard);
    writeFileSync(propsPath.replace(/\.json$/, `_v${it}.json`), JSON.stringify(s, null, 2), "utf8");
    console.log(`[loop] wrote props_v${it}.json (${patched} prop patches, ${changed.length} text rewrites)`);
    // re-render (child script) — replace with direct call for speed in tests
    const r = spawnSync("node", [join(ROOT, "autofix", "render.mjs"),
      "--project", project, "--composition", composition,
      "--out", join(project, "out", `${composition}_v${it}.mp4`),
      "--props", propsPath.replace(/\.json$/, `_v${it}.json`)],
      { encoding: "utf8", stdio: "inherit", shell: process.platform === "win32" });
    if (r.status !== 0) break;
    scorecard = scoreVideo(join(project, "out", `${composition}_v${it}.mp4`), title, python);
    console.log(`[loop] iteration ${it}: ${scorecard.verdict} ${scorecard.score}/100`);
  }
  console.log(`[loop] final: ${scorecard.verdict} ${scorecard.score}/100`);
}

if (process.argv[1] && process.argv[1].endsWith("loop.mjs")) main();