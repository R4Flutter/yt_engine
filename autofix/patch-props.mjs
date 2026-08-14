// M6 — deterministic props patches (PLAN.md Section 5, M6.2).
//
// Reads scorecard.json + your props/story JSON, applies deterministic
// transforms for the machine-actionable issues, writes props_v2.json.
//
// Supported patches (mapped from scorecard issue ids):
//   PACING_LOW / PACING_HIGH   -> scale scene durations (props.scenes[*].durationInFrames)
//   STATIC_SHOT                -> mark scene for trim (props.scenes[*].trim_sec)
//   LOUDNESS_LOW/HIGH          -> recorded for ffmpeg loudnorm post-pass (no props change)
//   TITLE_*                    -> replaced via --title flag / candidates.mjs
//
// Usage:
//   node autofix/patch-props.mjs props.json scorecard.json [out.json]
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { getPath, readJson, setPath } from "./lib.mjs";

const SCENE_PATH = "scenes";

function patchPacing(props, issue, target) {
  const scenes = getPath(props, SCENE_PATH);
  if (!Array.isArray(scenes) || !scenes.length) {
    console.log(`  [patch] ${issue.id}: no ${SCENE_PATH}[] in props — cannot patch pacing`);
    return 0;
  }
  const tooSlow = /(low|below|under|less than)/i.test(issue.detail || "");
  const factor = tooSlow ? 0.8 : 1.2; // 20% speed-up / slow-down
  let n = 0;
  for (const s of scenes) {
    if (s.durationInFrames) {
      const v = Math.max(30, Math.round(s.durationInFrames * factor));
      if (v !== s.durationInFrames) {
        s.durationInFrames = v;
        n++;
      }
    }
  }
  console.log(`  [patch] ${issue.id}: scaled ${n} scene durations by ${factor} (${tooSlow ? "tighter" : "slower"} pacing)`);
  return n;
}

function patchStaticShot(props, issue, target) {
  const scenes = getPath(props, SCENE_PATH);
  if (!Array.isArray(scenes)) return 0;
  // The issue detail says where the long static shot is; tag the scene and
  // let the rewrite/render decide. Deterministic: add a trim hint.
  for (const s of scenes) {
    if (s.durationInFrames) {
      s.trim_sec = s.trim_sec || Math.round(s.durationInFrames / 30 * 0.25 * 10) / 10;
      console.log(`  [patch] ${issue.id}: added trim_sec=${s.trim_sec} to "${s.label || s.id || "scene"}"`);
      return 1;
    }
  }
  return 0;
}

export function patchProps(props, scorecard, { loudness = true } = {}) {
  const issues = (scorecard.issues || []).filter((i) => i.ok === false);
  let patched = 0;
  const post = [];
  for (const issue of issues) {
    switch (issue.id) {
      case "PACING":
        patched += patchPacing(props, issue);
        break;
      case "STATIC_SHOT":
        patched += patchStaticShot(props, issue);
        break;
      case "LOUDNESS":
        post.push(`ffmpeg -i out/video.mp4 -af loudnorm=I=-14:TP=-1.5:LRA=11 out/video_loud.mp4`);
        console.log(`  [patch] ${issue.id}: audio post-pass queued (loudnorm to -14 LUFS)`);
        break;
      default:
        // text/manual issues → handled by rewrite.mjs / candidates.mjs
        break;
    }
  }
  return { patched, post };
}

function main() {
  const [propsPath, scorecardPath, outPath] = process.argv.slice(2);
  if (!propsPath || !scorecardPath) {
    console.error("usage: node autofix/patch-props.mjs props.json scorecard.json [out.json]");
    process.exit(1);
  }
  const props = readJson(propsPath);
  const scorecard = readJson(scorecardPath);
  console.log(`[patch-props] ${scorecard.verdict} (${scorecard.score}/100)`);
  const { patched, post } = patchProps(props, scorecard);
  const dest = outPath || propsPath.replace(/\.json$/, "_v2.json");
  writeFileSync(dest, JSON.stringify(props, null, 2), "utf8");
  console.log(`[patch-props] ${patched} props patched -> ${dest}`);
  for (const cmd of post) console.log(`[patch-props] post-pass: ${cmd}`);
}

if (process.argv[1] && process.argv[1].endsWith("patch-props.mjs")) main();