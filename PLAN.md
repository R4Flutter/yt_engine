# VIRALFORGE — YouTube Viral Intelligence Engine

**v3 — rewritten against the running system, 2026-08-13**
Finance & business stories · USA audience · free-tier

> `videogen/video` is a test consumer of this system's output, nothing more.
> VIRALFORGE owns the intelligence; renderers are swappable.

---

## 0. Current state (measured, not aspirational)

| Thing | State |
|---|---|
| Channels tracked | **26** (story_doc / explainer / investigation / personal_finance) |
| Videos in corpus | **1,189** |
| Retention heatmaps captured | **46** |
| Transcripts (word-timestamped) | **46** |
| **Aligned sentences** | **13,024** from 36 videos / 9 channels |
| Deep-crawl candidates remaining | **786** |
| Velocity snapshots | 0 — not yet scheduled |

**The bottleneck is corpus size, and nothing else.** Every model downstream is
starved until the deep crawl runs. 46 of 1,189 videos have heatmaps; the other
786 eligible ones are sitting in the queue.

---

## 1. The core insight (why this system is different)

Every YouTube growth tool scores videos against folklore — "hook in 15 seconds",
"4 words on a thumbnail" — advice repeated until it sounds like data.

There is a free, public, almost-unused source of ground truth: YouTube's
**"Most Replayed" graph**, exposed by yt-dlp as a `heatmap` field. It is a real
second-by-second record of where viewers rewatched and where they drifted, for
any video with enough views. Outliers reliably have it.

Joined to the word-timestamped auto-captions (also free, also yt-dlp), it
answers a question no blog post can:

> **Which sentences hold finance viewers, and which lose them?**

Not advice — coefficients, measured on your exact niche, before you publish
anything. That is `miner/alignment.py`, and everything else exists to feed it.

**Honest scope:** this stacks the odds; it cannot guarantee virality. YouTube
live-tests every upload on real viewers, and topic luck is real. What the system
buys you is never shipping a statistically weak video, and building from
measured patterns instead of guesses.

---

## 2. Hardware reality → engineering constraints

Audited on this machine:

| Resource | Reality | Consequence |
|---|---|---|
| CPU | Ryzen 5 5600H, 6c/12t | Cap workers at **4**, not 12 — RAM-bound, not CPU-bound |
| **RAM** | **7.3 GB total, ~1 GB free, 15.8 GB committed → already swapping** | **The binding constraint.** No local LLM. Stream from SQLite; never load the sentence table into pandas |
| GPU | AMD RX 6500M, **no CUDA** | faster-whisper runs CPU int8 only — use it sparingly |
| Disk | 357 GB free | Cache to disk instead of RAM |

### Three decisions this forces

**1. No local LLM on this box.** A 7B model at Q4 needs ~5 GB resident against
~1 GB free; Ollama would thrash the disk and make the desktop unusable.
`config/settings.yaml` sets `llm.provider: claude` — cents per video for the few
calls needing judgment. Everything else is deterministic code, which is faster,
free and reproducible anyway.

**2. Whisper never touches competitor videos.** They already ship
word-timestamped auto-captions for free. Transcribing 1,000 competitor videos on
this CPU would take weeks. Whisper (`base.en`, int8) runs only on your own
renders, via `analyzer/speech.py`.

**3. Don't download competitor video files.** The heatmap + transcript give you
retention and language — the two things that matter. Keep video downloads opt-in
for a small sample if you ever want cuts-per-minute stats.

---

## 3. Architecture (as built)

```
 harvester/ ──▶ db/ ──▶ miner/ ──▶ analyzer/ ──▶ autofix/ ──▶ [render]
  api_crawl     SQLite   alignment   score.py     patch+loop      │
  deep_crawl             outliers    media.py                     │
  discovery              hooks       speech.py                    ▼
  comments               titles      thumb.py               feedback/
                         thumbs      structure.py           analytics_pull
                         topics                             calibrate
                         heatmaps
                         report
```

| Module | Owns | Status |
|---|---|---|
| `harvester/api_crawl.py` | Quota-efficient API crawl, snapshots | built |
| `harvester/deep_crawl.py` | yt-dlp: heatmap, subs, thumbs | built — **786 queued** |
| `harvester/discovery.py` | New-channel search (100 units/query) | built |
| `miner/alignment.py` | **heat ↔ language regression** | **new, running** |
| `miner/{outliers,hooks,titles,thumbs,topics,heatmaps}.py` | Pattern mining | built |
| `miner/report.py` | Weekly `patterns_YYYY-WW.md` | built |
| `analyzer/{score,media,speech,thumb,structure}.py` | Score your own render 0–100 | built |
| `autofix/` | Props patch + re-render loop | built |
| `feedback/{analytics_pull,calibrate}.py` | Your real retention → recalibrate | built |

---

## 4. The alignment engine (`miner/alignment.py`)

The piece that makes this worth building. Runs offline on data already fetched.

**Pipeline:** heatmap → per-second curve · auto-caption words → utterances ·
join each utterance to the heat while it was spoken · featurize · fit.

### Segmentation is empirical, not assumed

YouTube auto-captions carry **no punctuation** — measured on this corpus, only
**1.13%** of word tokens end in `.!?`. So terminal punctuation cannot be the
boundary rule; pause length is all there is.

Measured word-gap distribution: p50 = 0.24 s, p75 = 0.40 s, **p95 = 0.80 s**.

| Threshold | Words per unit |
|---|---|
| 0.45 s (the original guess) | **5.3** — caption fragments |
| **0.80 s** | **18.0** — a real spoken sentence |
| 1.0 s | 122.9 — runs whole paragraphs together |

Splitting at 0.45 s produced 47,378 fragments like *"tariff Ori tariffs this is
a"*. A model fitted on those learns nothing about language. At 0.80 s the corpus
is 13,024 utterances averaging 18 words / 6.0 s. `MIN_WORDS`/`MAX_WORDS` guards
handle the cliff just above 0.8 s.

### Confound controls (the difference between a finding and a coincidence)

- **`heat_z` is normalized within each video** — otherwise the model just learns
  that popular videos are popular.
- **Position is residualized out before language is examined.** Retention vs
  position is a sharp spike then slow decay; a linear `rel_pos` term cannot
  absorb that, and the leftover leaks into whichever features cluster near the
  intro. The corpus-wide mean heat is subtracted per 50-bin position, so the
  question becomes: *given where we are in the runtime, did this line do better
  or worse than expected?*
- **Cross-validation groups by channel** — otherwise you learn one narrator's tics.
- **Bootstrap resamples videos, not sentences.** Sentences within a video are
  correlated; resampling them yields intervals that are far too narrow.

### What it currently says — and why you should not act on it yet

```
n = 13,024 sentences · 36 videos · 9 channels
held-out R² across channels: -0.13        confidence: LOW
```

**A negative R² means the model generalizes worse than predicting the mean.**
At this corpus size, sentence-level language features do **not** predict
within-video retention across channels. That is the honest result. The pipeline
is sound; the data is thin — 36 videos against a 200-video threshold, and 9
channels means each CV fold holds out only ~2.

Directional signals whose 95% interval excludes zero (hypotheses, not rules):

| Effect | Feature |
|---|---|
| **−0.078** | delivery speed (wpm) — *suspect: may be caption-timing artifact* |
| +0.027 | introduces a **new entity** |
| +0.022 | contrast ("but", "however") |
| +0.020 | names a company |

Re-run after the deep crawl. If R² is still negative at 200+ videos, the
conclusion is that sentence-level language is the wrong altitude and the signal
lives at beat/section level — which is itself worth knowing.

### The canonical retention curve

Averaged over 39 outliers, time-normalized: opening 10% = **0.298**,
middle = **0.232**, final 10% = **0.121**. Values are relative to each video's
own peak, so read it as shape, not level.

---

## 5. Quota & anti-block discipline

Daily API budget (of 10,000 units): 26 channels × playlist walk + `videos.list`
batched 50/call ≈ **~540 units**. You will never pay for API access.

- Never use `search.list` (100 units) for routine crawling — playlist walk is 1
  unit per 50 videos.
- yt-dlp runs from this home PC: **residential IP** (cloud IPs are broadly
  blocked). `sleep_requests: 3`, crawl at night, keep yt-dlp updated.
- If bot-checks start: uncomment `deep_crawl.cookies_from_browser: chrome`.
- **Do not** create extra API projects to multiply quota — that gets projects banned.

⚠️ **`api_crawl.py --once` prunes channels not in `config/seeds.yaml`.** A handle
that fails to resolve drops that channel and orphans its videos. After editing
seeds, always verify with `--resolve-only` first and check the resolved count.

---

## 6. Roadmap

| Phase | What | Done when |
|---|---|---|
| **NOW** | Deep-crawl the 786 queued videos | 300+ heatmaps, 25+ channels |
| **1** | Re-fit alignment | R² turns positive, or is ruled out at beat level |
| **2** | Velocity snapshots on a schedule | `snapshots` table non-empty; VPH radar live |
| **3** | Topic demand/supply gap finder | "high demand, low supply" list you'd make a video from |
| **4** | Packaging model (title+thumb → outlier score) | Ranks your 5 candidate titles |
| **5** | Feedback loop | Predicted vs actual on 5 published videos |

**Phase order is deliberate.** Everything after NOW is starved without corpus.

---

## 7. Immediate next actions

```bash
.venv/Scripts/python.exe -m harvester.deep_crawl --top 300
```
~2.5–4 hours unattended at 3 s politeness. Then:

```bash
.venv/Scripts/python.exe -m miner.alignment --rebuild --fit --curve
```

Schedule the crawl (Windows Task Scheduler): API crawl 06:00, snapshots every
6 h, deep crawl 07:00, weekly re-mine Sunday.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| **Heatmap missing / nulled** (recurring yt-dlp issue) | Track status, retry pass, keep yt-dlp updated; degrades to metadata+transcript |
| IP soft-ban | ≤150 req/h, 3 s sleeps, residential IP, night crawls, cookies fallback |
| **Spurious correlations** | Position residualized, grouped CV by channel, bootstrap over videos, effect sizes over p-values |
| Acting on low-n findings | `confidence: low` printed below 200 videos — treat as hypothesis |
| Unpunctuated captions | Empirical 0.80 s threshold + word-count guards (§4) |
| RAM exhaustion | Stream from SQLite, 4 workers max, no local LLM |
| API-upload private-lock | Un-audited projects force uploads to private — publish manually |

---

## 9. Sources

- [YouTube Data API quotas](https://developers.google.com/youtube/v3/getting-started) · [videos.insert private-lock](https://developers.google.com/youtube/v3/docs/videos/insert) · [Analytics API](https://developers.google.com/youtube/analytics)
- [yt-dlp heatmap support (#3888)](https://github.com/yt-dlp/yt-dlp/issues/3888) · [heatmap N/A regression (#8189)](https://github.com/yt-dlp/yt-dlp/issues/8189)
- [vidIQ — algorithm](https://vidiq.com/blog/post/understanding-youtube-algorithm/) · [OutlierKit — confirmed updates](https://outlierkit.com/resources/youtube-algorithm-updates/)
- [PrePublish — first 30 seconds](https://prepublish.ai/guides/first-30-seconds) · [SocialRails — retention curves](https://socialrails.com/blog/youtube-audience-retention-complete-guide)
- [1of10 — thumbnail psychology](https://1of10.com/blog/the-psychology-behind-high-ctr-thumbnails/) · [FluxNote — title formulas](https://fluxnote.io/guides/how-to-write-viral-youtube-titles-2026)
- [OutlierKit — finance RPM](https://outlierkit.com/blog/youtube-rpm-finance-niche) · [Overseeros — faceless finance channels](https://www.overseeros.com/blog/successful-faceless-finance-youtube-channels)
