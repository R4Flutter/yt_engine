// M6 Auto-Fix shared helpers (PLAN.md Section 5, M6).
// Plain ESM — run with: node autofix/lib.mjs (or import from other autofix/*.mjs)

import { spawnSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
export const REPORTS = join(ROOT, "reports");

// ---------------------------------------------------------------------------
// settings.yaml — minimal parser (provider + ollama/claude config only)
// ---------------------------------------------------------------------------
export function readSettings() {
  const raw = readFileSync(join(ROOT, "config", "settings.yaml"), "utf8");
  const s = { provider: "ollama", ollama: {}, claude: {} };
  const kv = (block, key) => {
    const m = raw.match(new RegExp(`${block}:\\s*([^\\n#]+)`));
    return m ? m[1].trim() : undefined;
  };
  s.provider = kv("provider", "") || s.provider;
  s.ollama.base_url = kv("base_url", "") || "http://localhost:11434";
  s.ollama.model = kv("model:", "") || "llama3.1:8b";
  const m = raw.match(/key_env:\s*(\w+)/);
  s.claude.key_env = m ? m[1] : "ANTHROPIC_API_KEY";
  return s;
}

// ---------------------------------------------------------------------------
// score a rendered video (calls the M5 python scorecard)
// ---------------------------------------------------------------------------
export function scoreVideo(videoPath, title, python = "python") {
  const args = ["-m", "analyzer.score", videoPath];
  if (title) args.push("--title", title);
  const r = spawnSync(python, args, {
    cwd: ROOT, encoding: "utf8", env: { ...process.env, PYTHONPATH: ROOT },
    maxBuffer: 64 * 1024 * 1024,
  });
  if (r.status !== 0) throw new Error(`score failed: ${r.stderr || r.stdout}`);
  const lines = r.stdout.split("\n");
  const lastJson = lines.slice(0, -2).join("\n"); // drop trailing [scorecard] line
  return JSON.parse(lastJson);
}

// ---------------------------------------------------------------------------
// LLM call — ollama | claude | off (fallback returns null)
// ---------------------------------------------------------------------------
export async function llm(prompt, { settings = readSettings(), timeoutMs = 120000 } = {}) {
  const p = settings.provider;
  if (p === "off") return null;
  if (p === "ollama") {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(`${settings.ollama.base_url}/api/generate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ model: settings.ollama.model, prompt, stream: false }),
        signal: ctrl.signal,
      });
      if (!res.ok) return null;
      const data = await res.json();
      return (data.response || "").trim();
    } catch {
      return null;
    } finally {
      clearTimeout(t);
    }
  }
  if (p === "claude") {
    const key = process.env[settings.claude.key_env];
    if (!key) return null;
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json" },
        body: JSON.stringify({ model: settings.claude.model || "claude-haiku-4-5-20251001", max_tokens: 800, messages: [{ role: "user", content: prompt }] }),
        signal: ctrl.signal,
      });
      if (!res.ok) return null;
      const data = await res.json();
      return (data.content?.[0]?.text || "").trim();
    } catch {
      return null;
    } finally {
      clearTimeout(t);
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// JSON helpers
// ---------------------------------------------------------------------------
export function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

export function setPath(obj, path, value) {
  const parts = path.split(".");
  let cur = obj;
  for (const p of parts.slice(0, -1)) {
    if (cur[p] == null || typeof cur[p] !== "object") cur[p] = {};
    cur = cur[p];
  }
  cur[parts[parts.length - 1]] = value;
  return obj;
}

export function getPath(obj, path) {
  let cur = obj;
  for (const p of path.split(".")) {
    if (cur == null) return undefined;
    cur = cur[p];
  }
  return cur;
}

export { existsSync };