// M6 — LLM script rewrite (PLAN.md Section 5, M6.3).
//
// Reads scorecard issues + hooks_library.json (M3 verbatim outlier hooks),
// asks the LLM to rewrite the weak hook/scene text grounded in real examples.
// Falls back to returning the original text when LLM is unavailable.
//
// Usage:
//   node autofix/rewrite.mjs script.json scorecard.json [out.json] [--dry]
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { REPORTS, llm, readJson, readSettings, setPath } from "./lib.mjs";

const HOOK_ISSUES = ["HOOK_SLOW", "HOOK_PROMISE", "HOOK_PACE"];

function hookExamples() {
  const p = join(REPORTS, "hooks_library.json");
  if (!existsSync(p)) return [];
  return readJson(p).slice(0, 6);
}

export async function rewriteScript(script, scorecard, { dry = false } = {}) {
  const issues = (scorecard.issues || []).filter((i) => i.ok === false);
  const hookIssue = issues.find((i) => HOOK_ISSUES.includes(i.id));
  const changed = [];
  const examples = hookExamples();

  // 1. Find the hook text in the script (common shapes: hook.lines, hook.text, scenes[0].text)
  const hookTarget = findHookTarget(script);
  if (hookIssue && hookTarget) {
    const current = getText(script, hookTarget);
    const ex = examples.map((e) => `- [${e.archetype}, ${e.outlier_score}x] ${e.title}: "${e.hook_text}"`).join("\n");
    const prompt = `You are a finance documentary editor. Rewrite the opening hook of a video so the payoff promise lands within 8 seconds and a pattern interrupt opens the first 5 seconds. Ground it in these REAL viral hooks (titles + first-30s):

${ex || "(no examples available — use bold claim + specific number + open loop)"}

Current hook: "${current}"
Scorecard issue: ${hookIssue.id} — ${hookIssue.detail}
Fix instruction: ${hookIssue.fix?.instruction || ""}

Reply with ONLY the rewritten hook text, 1-3 short sentences.`;
    const rewritten = dry ? null : await llm(prompt);
    if (rewritten && rewritten.length > 5) {
      setPath(script, hookTarget.join("."), rewritten);
      changed.push({ target: hookTarget.join("."), before: current, after: rewritten });
      console.log(`  [rewrite] HOOK: "${current.slice(0, 60)}..." -> "${rewritten.slice(0, 60)}..."`);
    } else {
      console.log(`  [rewrite] LLM unavailable (provider=${readSettings().provider}) — hook left as-is`);
    }
  }

  // 2. TITLE — propose replacement when title issues exist
  const titleIssue = issues.find((i) => i.id.startsWith("TITLE_"));
  if (titleIssue && script.title) {
    const current = script.title;
    const prompt = `Rewrite this YouTube title to hit: <=60 chars, specific odd number or curiosity gap, finance niche. Current: "${current}". Issue: ${titleIssue.detail}. Reply with ONLY the new title, no quotes.`;
    const rewritten = dry ? null : await llm(prompt);
    if (rewritten && rewritten.length > 3) {
      setPath(script, "title", rewritten);
      changed.push({ target: "title", before: current, after: rewritten });
      console.log(`  [rewrite] TITLE: "${current}" -> "${rewritten}"`);
    }
  }
  return changed;
}

function findHookTarget(script) {
  if (typeof script.hook === "object") return ["hook", "lines"];       // videogen style
  if (script.hook) return ["hook"];
  if (Array.isArray(script.scenes) && script.scenes[0]?.text) return ["scenes", "0", "text"];
  if (script.hook_text) return ["hook_text"];
  return null;
}

function getText(script, target) {
  let cur = script;
  for (const p of target) {
    if (cur == null) return "";
    cur = cur[p];
  }
  return Array.isArray(cur) ? cur.map((x) => typeof x === "string" ? x : x.text || "").join(" ") : String(cur || "");
}

async function main() {
  const args = process.argv.slice(2).filter((a) => a !== "--dry");
  const [scriptPath, scorecardPath, outPath] = args;
  const dry = process.argv.includes("--dry");
  if (!scriptPath || !scorecardPath) {
    console.error("usage: node autofix/rewrite.mjs script.json scorecard.json [out.json] [--dry]");
    process.exit(1);
  }
  const script = readJson(scriptPath);
  const scorecard = readJson(scorecardPath);
  const changed = await rewriteScript(script, scorecard, { dry });
  const dest = outPath || scriptPath.replace(/\.json$/, "_v2.json");
  writeFileSync(dest, JSON.stringify(script, null, 2), "utf8");
  console.log(`[rewrite] ${changed.length} text blocks rewritten -> ${dest}${dry ? " (dry run, no LLM call)" : ""}`);
}

if (process.argv[1] && process.argv[1].endsWith("rewrite.mjs")) main();