# M4 — Hook Intelligence System: Final Report (measured, not aspirational)

Date: 2026-08-14 · Scope: learned pattern library + per-horizon ML + honest
predictions, integrated into generation and the dashboard.

## 1. What changed

| File | Change |
|---|---|
| `db/schema.sql` | + `hook_training_examples` (12 numeric + 5 categorical + 26 binary features, 5 retention targets, channel_id/niche_tag, indexes) · + `learned_patterns` (pattern_key, scope, kind, feature, effect_z, ci95_lo/hi, robust, channel_consistency, confidence, best_niche, best_duration_sec) |
| `miner/hook_learn.py` | **new** — the entire learning layer (features, training-set build, encoding, GroupKFold validation, per-horizon training + versioning, prediction + per-feature contributions, pattern/interaction discovery, pattern evidence, actuals calibration) |
| `miner/hook_gen.py` | generation gains learned dimensions (D2: model prediction, pattern evidence; F2: ranking) — active ONLY when a real model/pattern exists |
| `miner/hooks.py` | CLI: `train`, `patterns-learned`, `predict`, `benchmark-model` |
| `config/settings.yaml` | scoring weights `learned: 10`, `pattern_evidence: 10` |
| `dashboard/app.py` | Hooks tab: model table, pattern library, retention predictor |
| `tests/test_hook_learn.py` | **new** — 23 tests for the learning stack |
| `PLAN.md` | §6b documents the M4 system |

## 2. Dataset

- 1,189 videos · 46 transcripts/heatmaps · 49 library hooks · **36 hooks with
  text + full retention** across **9 channels** (MagnatesMedia 18/36 = 50%).
- Targets: per-horizon retention z (within-video, 3/5/10/15/30 s).
- Truth: `retention_10s` min −0.57 · median 2.52 · max 7.83.

## 3. Model architecture

- Per horizon: **Ridge** (interpretable) + **HistGradientBoosting** (nonlinear),
  one-hot categories (with `other` bucket), median-imputed timings, GroupKFold
  (k=5) **by channel** — no channel appears in both train and validation folds.
- **Gate:** a model is kept only if CV RMSE is ≥5% better than the median
  baseline. Versioned `data/models/hook_{h}s_vNNN.joblib` + `.meta.json`;
  nothing is ever overwritten.
- Confidence (Phase 21): n<20 INSUFFICIENT DATA · 20–49 LOW · 50–149 MEDIUM ·
  150+ HIGH (robust CI required).

## 4. Measured results (this machine, Ryzen 5 5600H / CPU)

| Metric | Value |
|---|---|
| Training-set build | 36 rows in 0.05 s · peak 0.1 MB · 752 rows/s |
| Full train (5 horizons, 2 model classes, GroupKFold) | 15.6 s · **peak 10.3 MB** (target <3 GB, hard cap 5 GB) |
| Model sizes | ~3 KB each (baseline stores medians only) |
| Generation warm path | 0.177 s (unchanged — learning adds ~0 skipped when no models) |
| Dashboard | boots, 0 exceptions, 7 dataframes |

**Honest verdict: at n=36 no horizon beats the baseline.** All 5 horizons stored
`kind=baseline`, improvement +0.0%. Predictions therefore equal the corpus
median per horizon with confidence LOW — exactly what the system must say.

## 5. Learned patterns (n=36, scope GLOBAL — all LOW confidence)

Strongest signals (95% bootstrap CI over videos, channel-consistent):

| Pattern | effect z | 95% CI | ch | best @ |
|---|---|---|---|---|
| STRUCT contradiction | +1.266 | [−0.25, +2.42] | 3/5 | 5 s |
| open loop | +0.785 | [−0.75, +2.02] | 4/5 | 10 s |
| shock + open loop | +0.947 | [−0.32, +2.46] | 2/5 | 5 s |
| curiosity before 5 s | +0.714 | [−0.62, +2.10] | 3/5 | 5 s |
| has percent | −1.687 | [−2.81, 0.00] | 1/5 | 10 s |
| promise before 10 s | −1.346 | [−2.27, 0.00] | 0/5 | 10 s |

22 of 31 candidate patterns survived the evidence floor (n≥5 hooks). All CIs
span zero → nothing is actionable yet, and nothing is claimed to be.

## 6. How learned intelligence affects ranking

- Generation consults the latest model + GLOBAL patterns only if they exist;
  a baseline model never counts as influence (`learned_enabled` /
  `patterns_enabled` + per-hook `learned_influenced_rank`, honest flags).
- `pattern_evidence` attaches the matching pattern + CI + confidence to each
  hook; the `pattern_evidence` dimension folds the effect z into the score
  (weight 10) only when matched.

## 7. New CLI

```bash
python -X utf8 -m miner.hooks train --build        # build set + fit + version models
python -X utf8 -m miner.hooks patterns-learned     # discover + write learned_patterns + reports/
python -X utf8 -m miner.hooks predict "topic"      # top hooks + per-horizon predictions
python -X utf8 -m miner.hooks predict --text "..." --json
python -X utf8 -m miner.hooks benchmark-model      # RAM / time / rows-per-sec
```

Example prediction (real run): "Why does Lamborghini make so much money?" →
3 s +2.85 z · 5 s +2.80 · 10 s +2.52 · 15 s +1.86 · 30 s +0.41, confidence LOW
(all horizons = corpus median; model gate closed).

## 8. Limitations (said out loud)

1. **n=36 is not a training corpus.** Every learned output is labeled LOW or
   INSUFFICIENT DATA; the system refuses to fake certainty.
2. MagnatesMedia = 50% of labels; GroupKFold contains the leakage, it cannot
   remove the bias — patterns describe mostly one channel's style.
3. One row per video, so interactions at n=36 have near-zero power; the
   interaction set is curated (15 combos), not exhaustive.
4. Feedback calibration (`calibrate_from_actuals`) is built and tested but
   idle: it needs ≥5 generations with `actual_avd_pct` and ≥10 hook-level
   pairs to fit.

## 9. Next improvement (corpus-driven, in order)

1. Deep-crawl to ≥150 labeled hooks (open the model gate; re-run
   `train --build`).
2. Re-run `patterns-learned` at n≥50 — expect the first MEDIUM-confidence
   patterns.
3. Link real published outcomes (`record-outcome`) → `calibrate_from_actuals`
   reweights HookScore from observed performance.