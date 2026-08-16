# Script Writer → video_engine

`miner/script_writer.py` is the writing layer for the video engine. It is deliberately separate from Shorts generation.

## What it produces

For a topic it creates two artifacts:

- `*.json` — machine-readable contract for downstream automation.
- `*.md` — human-readable brief + script.

The JSON contains:

- topic/profile/runtime/target narration words
- long-form hook contract
- retention-device map
- act architecture
- writing rules
- evidence rules
- generated script (when `--llm` is used)
- validation score/errors/warnings

## Recommended 20-minute workflow

```powershell
python -m miner.script_writer "The Company That Sells You Nothing" `
  --minutes 20 `
  --fact "Planet Fitness has about 18.7 million members" `
  --fact "The company operates roughly 2,500 gyms" `
  --fact "..." `
  --llm `
  --out data/script_runs/company-sells-nothing
```

The facts should come from research. The writer is forbidden from treating a plausible number as a verified fact.

## Long-form hook contract

The writer does **not** use the Shorts rule of constant immediate stimulation.

The default documentary cold open has three layers:

1. **Observation / visual first** — establish a concrete situation and let the viewer notice something is wrong.
2. **Evidence arrives** — introduce specific evidence one piece at a time.
3. **Hook claim lands** — state the larger contradiction after tension has accumulated.

The exact timing is generated as a scaffold and can be changed by the director. The principle is more important than a fixed second count.

## Long-form retention model

The engine plans narrative events rather than 2-second cuts:

`cold open → new entity → reversal → new entity/reversal → number spike → new entity → reversal → landing/reframe → hard stop`

Every act must:

- answer a question created earlier,
- create a new useful question,
- add new evidence/entity/mechanism/reversal,
- avoid repeating the same explanation.

This prevents the video engine from turning a 20-minute documentary into a stretched Shorts edit.

## Evidence discipline

The writer distinguishes:

- **OBSERVED** — supplied/measured evidence.
- **INFERRED** — interpretation derived from evidence.
- **CREATIVE_FRAMING** — narration language used to make the story clear/interesting.
- **verification_required** — a claim that must be checked before publication.

Numbers, dates, names, legal events and quotations should never be invented.

## CPU/RAM design

The planning and QC path is standard-library based and lightweight. Full prose generation is optional and remote through the configured Claude provider, so the writing engine does not require a local 7B/14B model or GPU.

## Relationship to existing yt_engine intelligence

The existing hook intelligence remains the evidence source for hook design. Its M4 report found structural contradiction, open loops, shock + open loop and early curiosity among the strongest observed patterns, but explicitly labels the current training corpus low-confidence and does not claim universal causality. The script writer therefore uses those patterns as design constraints, not as guarantees.

The existing Company Sells Nothing reference script supplies the documentary register: measured delivery, clean number pauses, historical/business reversals, new-entity transitions and a hard-stop reframe.
