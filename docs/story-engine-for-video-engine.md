# Story Engine → video_engine

`miner/story_engine.py` is an additive writing-intelligence layer. It does **not** modify the existing Shorts engine or long-form engine.

## Purpose

Turn research + verified facts + hook candidates into a machine-readable business-story blueprint that `video_engine` can consume before narration/directing.

## Pipeline

```text
research/facts
    ↓
existing yt_engine hook intelligence
    ↓
Hook DNA validation
    ↓
miner/story_engine.py
    ↓
hook ranking + cold-open contract + narrative arc
    ↓
script_writer.py / external LLM
    ↓
video_engine
```

## Long-form writing principles

- contradiction before explanation
- evidence before hype
- question → evidence → answer → new question
- reversals change the meaning of earlier evidence
- new entities/mechanisms create genuine state changes
- numbers must advance the argument
- visual changes follow meaning, not a 2-second stopwatch
- opening motif returns in the final reframe
- hard stop after payoff

## Hook scoring

The deterministic layer rewards contradiction, open loops, specificity, named entities, evidence/numbers, explicit questions and usable length. It penalizes generic clickbait and unresolved tension.

This is a **writing QA score**, not a views prediction.

## CPU/RAM

The module uses Python stdlib plus the existing deterministic `hook_dna` system. No local LLM is required. If an LLM is used for the full draft, keep it remote so the writing stage does not consume the 16 GB video-render machine's RAM.

## Example

```powershell
python -m miner.story_engine "The Company That Sells You Nothing" `
  --thesis "Subscription businesses can make money from customers who barely use the service." `
  --fact "20.8 million members" `
  --fact "2,896 clubs" `
  --hook "An empty gym can be more valuable than a full one." `
  --hook "Twenty million people can pay for something they barely use. Why?" `
  --out data/story_runs/company-sells-nothing
```

The output contains both `.json` and `.md` artifacts for downstream `video_engine` use.
