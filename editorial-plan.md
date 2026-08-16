# THE COMPANY THAT SELLS YOU NOTHING — 19:14 EDITORIAL PLAN

**Episode:** Real Return #01  
**Runtime target:** 19:14 exact  
**Source script:** `new_story_script.md`  
**Editorial companion:** `R4Flutter/video_engine/prompt/editing-director-19m.md`  
**Primary pipeline:** `yt_engine` intelligence → script/beat structure → `video_engine` world/asset manifest → director plan → voice → alignment → QC → render/master → `yt_engine` score → revise  
**Editorial objective:** premium investigative business documentary; faceless; evidence-first; no “AI slideshow” feeling; retention comes from discovery, contrast, evidence and reversals rather than nonstop motion.

> This file is the scene-by-scene execution contract. It does **not** invent a new visual language. It converts the existing story and editing-director rules into explicit scene actions, asset classes, motion, sound, text, retention purpose, and exit conditions.

---

## 0. PIPELINE CONTRACT — DO THIS IN ORDER

The `yt_engine` repo explicitly treats the intelligence layer as upstream of the renderer: its corpus/heatmap/alignment/hook systems mine what holds attention, while `video_engine` is a consumer/renderer. The current `yt_engine` plan also says the strongest defensible retention signal comes from YouTube heatmaps aligned to word-timestamped captions, and warns against treating low-sample correlations as rules. `new_story_script.md` already encodes the current retention-device map for this episode.  
Sources: `PLAN.md`, `new_story_script.md`.

### Stage A — Intelligence lock

1. Use the episode's existing hook thesis: **the subscription economy monetizes the gap between intention and action**.
2. Protect the measured device positions already selected in the script: roughly 18%, 29%, 39%, 57%, 70%, 82%, 92% of runtime.
3. Treat every number in the script as **FACT-CHECK REQUIRED** until verified against a primary source.
4. Do not move a major reveal later merely to “make the edit prettier.”
5. Do not force a cut rate. `video_engine`'s rule is: **cut because meaning changed**.

### Stage B — Story parse

Create one machine-readable beat per scene with:

`scene_id, start, end, chapter, narration_range, viewer_question, retention_device, primary_visual, secondary_visual, text, motion, transition_in, transition_out, music_state, sfx, asset_id, evidence_level, source, notes`

The scene IDs in this document are canonical. Keep them stable across revisions so `director-plan.json`, asset manifests, QC notes, and score feedback can be diffed.

### Stage C — World / asset build

For each scene, prefer:

1. authentic evidence / source document
2. specific realistic B-roll
3. specific subject/environment still
4. explanatory graphic
5. typographic card
6. decorative atmosphere

Use real-world objects and interfaces only where they communicate the sentence. Do not use generic “business people in office” footage as filler.

### Stage D — Director pass

For each scene, answer:

- what must be understood?
- what should be felt?
- what proves it fastest?
- what changes during the scene?
- what must remain long enough to read?
- what question pulls into the next scene?

### Stage E — Voice + alignment

Target the script's measured **170 wpm**. Preserve the specified pauses before dollar figures and major reveals. Generate voice, align it, then use the actual aligned durations as the timing authority. Do **not** force every scene to a precomputed duration if narration alignment differs by a few frames; preserve the story beats and rebalance adjacent holds.

### Stage F — Render + QC

Run the repository pipeline in its intended order:

`script → director plan → voice → align → gate/QC → render → master → viral score`

The current video-engine pipeline documentation also describes `yt_engine` as the source for hook/pattern intelligence and the rendered video being sent back to a viral score/QC loop. See `video_engine/docs/pipeline.html`.

### Stage G — Revision loop

A failed score is not permission to sprinkle more zooms. Classify the problem:

- **story:** weak question/reward
- **evidence:** claim not shown/proven
- **visual:** wallpaper/repetition
- **rhythm:** too slow or artificially busy
- **audio:** music/sfx flattening hierarchy
- **text:** too much or poorly timed
- **ending:** summary/outro creates late drop

Then revise the smallest layer capable of fixing the problem.

---

# 1. FACT-CHECK LOCK — CURRENT RESEARCH NOTES

The existing script contains several numbers/claims that have changed or need more precise sourcing. The editorial plan should **not** quietly preserve stale figures.

### Planet Fitness
The script currently opens with 18.7M members and ~2,500 gyms. Planet Fitness' 2025 10-K says **approximately 20.8M members and 2,896 clubs at year-end 2025**, with 2025 revenue of about $1.3B and system-wide sales of $5.3B. It also says clubs are typically about 20,000 square feet and the Classic Card membership started at $15/month for new members. Use the 2025 figure in graphics unless the exact episode thesis requires the older historical number.  
Primary source: SEC, Planet Fitness 2025 10-K.

### $86 vs $219 subscription-spend figure
The $86 estimate versus $219 itemized amount is supported by C+R Research's subscription study, with a $133 gap. C+R also reports that 74% of respondents said it was easy to forget recurring monthly subscription charges. Treat this as **survey evidence**, not an absolute “average American household today” fact. Put the study label/date on-screen and avoid implying it is a 2026 government statistic.  
Primary source: C+R Research.

### Adobe
Adobe's FY2023 SEC filing says **Creative Cloud revenue was $11.517B** and **Digital Media revenue was $14.216B**; total Adobe FY2023 revenue was $19.41B. The script's phrasing about “Creative Cloud revenue from $1.23B in 2013 to $18.28B in 2023” should be rechecked against the exact metric before recording; do not display a metric mismatch. Prefer the SEC-defined segment/offerings numbers.  
Primary source: SEC Adobe 2023 10-K / FY2023 results.

### Amazon / Prime settlement
The FTC says the September 25, 2025 settlement totals **$2.5B: $1B civil penalty + $1.5B consumer refunds** and requires Amazon to change Prime enrollment/cancellation practices, including a clear decline button and cancellation through the same method used to sign up. The FTC says refunds/claims continued into 2026. This is strong primary-source evidence and should be shown as evidence, not generic stock footage.  
Primary source: FTC, September 25, 2025 settlement.

### Click-to-cancel rule
The Eighth Circuit's July 8, 2025 opinion vacated the FTC's 2024 rule, concluding the FTC had failed to complete required preliminary regulatory analysis. The FTC's current Negative Option Rule page shows the agency began an amended rulemaking process again in March 2026. Therefore the line “there is no federal click-to-cancel rule in effect” must be checked against the exact legal scope and any later federal developments immediately before recording.  
Primary sources: Eighth Circuit opinion, FTC Negative Option Rule page.

### Streaming
The script's “4.7 services / $61” figure is not stable across surveys. Deloitte's 2025 Digital Media Trends reports an average of **4 paid SVOD services and $69/month** among subscribing households in its surveyed population; its 2026 release again reports $69/month. Morgan Stanley's 2026 survey reports **5.4 streaming services** when free and paid services are both counted. Pick one methodology and label it. Do not combine incompatible survey definitions.  
Primary sources: Deloitte 2025/2026 Digital Media Trends; Morgan Stanley 2026 streaming survey.

---

# 2. MASTER VISUAL RULES

## Viewer hierarchy

**Primary:** one dominant object/number/idea.  
**Secondary:** supporting context.  
**Texture:** atmosphere only.

Never show five facts at equal visual weight.

## Motion vocabulary

- **LOCKED** = evidence / authority
- **SLOW PUSH** = importance growing
- **SLOW PULL** = perspective widening
- **PUNCH** = decisive information
- **DRIFT** = exploration / transition
- **SETTLE** = payoff / ending

## Default transitions

Hard cut first. Use J-cuts/L-cuts when they smooth narrative progression. Use match cuts and graphic bridges only when the relationship itself is meaningful. No generic zoom transitions, spins, template glitches, or constant whooshes.

## Long-form text rule

Use selective editorial typography, **not karaoke captions**.

- **HERO:** 1–7 words
- **SUPPORT:** short context/date
- **SOURCE:** source/date/qualifier

Every on-screen claim with legal/financial significance should have source context in the final evidence package.

## Evidence rule

If a claim is consequential and an authentic document exists, use the document. Do not substitute AI-looking “courtroom stock footage” for primary evidence.

## Silence rule

Major reveals should often get quieter. Silence before:

- BREAKAGE
- Adobe ownership reversal
- ILIAD
- $2.5B
- PROCEDURE
- final callback

---

# 3. COMPLETE 19:14 SCENE PLAN

The following timings are **editorial anchors**, not immutable frame locks. Voice alignment is authoritative. Scene durations should land within the stated ranges while preserving the narrative device at the same relative point.

| ID | Time | Story / narration | What the viewer sees | Edit / motion | Text / evidence | Audio / retention job |
|---|---|---|---|---|---|---|
| S01 | 00:00–00:06 | Cold open: empty Planet Fitness | Empty gym at 4am, wide locked frame, one distant treadmill later visible | **LOCKED**, no move for full 6s | None | Fluorescent hum only; establish mystery |
| S02 | 00:06–00:16 | “18.7M” / current member contradiction | Same gym; faint member-count layer enters | Slow push begins only as number lands | **MEMBERS** + verified current figure; source small | Single low pulse; question: how can this room support them? |
| S03 | 00:16–00:28 | Clubs / arithmetic | Gym exterior → map/grid of clubs | Hard cut; number builds in 2 stages | `MEMBERS / CLUBS` then derived members-per-club | No extra SFX; let viewer calculate |
| S04 | 00:28–00:38 | Typical club / occupancy | Floor plan / 20k sq ft room + occupancy overlay | Progressive reveal | `~20,000 SQ FT` + verified occupancy source | Music rises slightly; contradiction resolves |
| S05 | 00:38–00:40 | “This is the product.” | Return to empty gym | Smash cut to stripped frame | **THIS IS THE PRODUCT.** | Music stops for line; first major thesis sting |
| S06 | 00:40–00:52 | $86 estimated | Phone/bank statement visual, clean | Slow vertical scroll | **$86** / subscription estimate + source | Clean investigative bed |
| S07 | 00:52–01:04 | $219 actual | Same statement; recurring charges accumulate | Cards/charges stack one by one | **$219** | Low tick per layer; number spike |
| S08 | 01:04–01:18 | $133 gap | 86 → 219 bridge | Number morph, then settle | **+$133 / MONTH** | Silence under reveal; retention spike |
| S09 | 01:18–01:35 | System was built | “free trial” screen / recurring charge / cursor | Drift across details | **NOT CARELESSNESS** | Bed grows; unanswered “how?” launches Act I |
| S10 | 01:35–01:50 | Start with gym | 1980s/1990s health club archive | Slow dissolve from present to archival | `THE GYM` | VHS texture; new chapter |
| S11 | 01:50–02:10 | Fixed costs | Simple cost diagram: building/lease/lights | Nodes appear in narration order | `FIXED COSTS` | Stable pulse; teach mechanism |
| S12 | 02:10–02:30 | Marginal member economics | Revenue line vs service-cost line | Lines draw only while relation is explained | **PAYING / SHOWING UP** | One subdued rise |
| S13 | 02:30–02:47 | Ideal customer | Empty gym + membership account | Micro-push into inactive membership | **PAYS / DOESN'T COME** | Strip music for 1 beat |
| S14 | 02:47–03:03 | Unused memberships | Empty machines / January membership imagery | Match cuts between empty room and unused card | Source label for unused-membership estimate | Keep factual and restrained |
| S15 | 03:03–03:18 | January intention | Google Trends-style chart / seasonal spike | One-year loop, then multi-year stack | **JANUARY → FEBRUARY** | Tiny rhythmic accent on collapse |
| S16 | 03:18–03:25 | Define breakage | Black frame | Full stop | **BREAKAGE** | **1.5s silence**; retention device peak |
| S17 | 03:25–03:48 | Gift cards / miles / store credit | Gift card drawer → airline miles UI → store credit | 3 conceptual match cuts | `ONE-TIME BREAK` | Light texture; explain predecessor |
| S18 | 03:48–04:12 | Subscription repeats breakage | Calendar pages with recurring charge | Charge repeats down-frame | **EVERY MONTH** | Tick repeats, then drops out |
| S19 | 04:12–04:30 | Bally enters | 1990s Bally signage / storefront | Locked archive + subtle parallax | **BALLY TOTAL FITNESS** | Shift to colder tension |
| S20 | 04:30–04:52 | Long contracts | Contract close-up / signature / small print | Detail reveal | **3 YEARS** only if source confirms exact example | Paper texture; evidence tone |
| S21 | 04:52–05:08 | 1994 investigation | Regulatory / consumer documents | Page turn to cited section | `1994` + agency/source | Music down; document authority |
| S22 | 05:08–05:25 | Later complaints | Newspaper / complaint-form montage | 4–5 evidence clips, not decorative montage | `600+ COMPLAINTS` only if source verified | No dramatic boom; let evidence work |
| S23 | 05:25–05:35 | Why contract model failed | Contract dissolves into complaint → regulator → settlement chain | Causal diagram | **THE CONTRACT WAS THE WRONG TOOL** | Silence before line; reversal peak |
| S24 | 05:35–05:52 | Planet Fitness reversal | Bright modern Planet Fitness exterior | Hard reset, brighter exposure | **NO THREE-YEAR TRAP** only if legally accurate | Bed lightens |
| S25 | 05:52–06:10 | Leaving is legal but costly in effort | Cancellation flow recreation | Slow cursor path | **EFFORT IS THE FRICTION** | Mouse click foley only |
| S26 | 06:10–06:30 | $10 threshold | Bank statement; $10 charge surrounded by noise | PUNCH on charge, then pull back | **$10 / MONTH** → **$120 / YEAR** | Two notes: small monthly / large yearly |
| S27 | 06:30–06:48 | Adobe physical software reset | Photoshop CS6 box / disc / license key | Slow turntable-like move | **OWNED** | Hard cut + broader room tone |
| S28 | 06:48–07:08 | Old ownership model | Box + dated desktop UI | Locked / slight drift | `BUY ONCE` | Calm explanatory bed |
| S29 | 07:08–07:30 | Sawtooth revenue | Adobe revenue chart with release-cycle spikes | Line draws, pauses at each spike | `REVENUE ARRIVES IN SPIKES` | Subtle pulse synchronized to spikes |
| S30 | 07:30–07:50 | May 6, 2013 | Adobe MAX stage archive | Push toward date card | **MAY 6, 2013** | Music thins before announcement |
| S31 | 07:50–08:10 | Creative Suite is finished | Forum/headline/Adobe announcement evidence | Fast 4–5 item burst then hold | **CREATIVE SUITE: FINISHED** | Fast montage for shock |
| S32 | 08:10–08:30 | Subscription reaction | Petition / forum / headlines | Layered evidence board, then clear | `REACTION` / source/date | Keep dry, no rage music |
| S33 | 08:30–08:48 | Ownership reversal | CS6 box → subscription card | Match cut on rectangular shape | **OWNED → RENTED** | One low-frequency transition |
| S34 | 08:48–09:08 | Adobe revenue consequence | Verified SEC revenue / segment chart | Reveal one metric at a time | Use **Creative Cloud** or **Digital Media** metric consistently | Number accent |
| S35 | 09:08–09:30 | 2013 vs 2023 | Two-column evidence frame | Count-up or slide, then freeze | **2013 / 2023** + source | Music broadens |
| S36 | 09:30–09:54 | Not 15× better | Photoshop evolution / interface comparison | Split-screen with locked framing | **THE PRODUCT DIDN'T CHANGE 15×** only if phrased as editorial opinion, not stat | Remove music for line |
| S37 | 09:54–10:20 | What changed: ownership | Subscription contract / account screen / Adobe stock-room | Slow push across “ownership” concept | **OWNERSHIP CHANGED** | Mechanism clarity reward |
| S38 | 10:20–10:55 | Backlash doesn't stop subscription | Boardroom generic only briefly, then customer billing UI | L-cut into next world | **ANGER ≠ CHURN** only if positioned as editorial synthesis | Tease cable/streaming |
| S39 | 10:55–11:12 | Cable was the hated bundle | 2007 cable bill | Document hold | **THE BUNDLE** | Reset visual language |
| S40 | 11:12–11:30 | Streaming promised escape | Netflix red-envelope/early UI | Warm archival dissolve | **NO CONTRACT / CANCEL ANY TIME** | Nostalgic texture |
| S41 | 11:30–11:52 | Studios split catalogue | Service cards separate across screen | Cards split from one library | `NETFLIX / HULU / PRIME / ...` as needed | Accumulating clicks |
| S42 | 11:52–12:05 | Stack grows | Streaming logos/cards multiply | One new card per concept, not logo parade | **4–5 SERVICES** only with chosen methodology | Music grows then cut |
| S43 | 12:05–12:24 | “Which is the opposite?” | Amazon Prime signup | Hard cut into modern UI world | **AMAZON** | New colder palette |
| S44 | 12:24–12:45 | FTC suit / button | Recreated signup flow | Cursor demonstrates misleading hierarchy | `ENROLL` vs `DECLINE` | Sparse clicks; no cartoon arrows |
| S45 | 12:45–13:05 | Millions enrolled allegation | Source document / FTC complaint excerpt | Document crop + highlight key paragraph | `FTC ALLEGES…` + date | Evidence authority |
| S46 | 13:05–13:20 | Cancellation maze | UI sequence | Each page becomes next, no flashy transition | Small chapter marker **THE CANCELLATION** | Tension rises |
| S47 | 13:20–13:40 | Iliad | Black frame → one word | Full visual isolation | **ILIAD** | **2s silence** then faint room tone |
| S48 | 13:40–13:58 | Homer naming explanation | Old Iliad book / pages | Slow push | **TEN-YEAR WAR** | Single low sustained tone |
| S49 | 13:58–14:12 | Trial / settlement | FTC official page / settlement document | Scroll to order date | **SEP 25, 2025** | Music drops |
| S50 | 14:12–14:34 | $2.5B | Black or neutral evidence plate | Number appears in 2 states | **$2.5 BILLION** | Silence + one restrained impact |
| S51 | 14:34–14:50 | Split penalty/refunds | Diagram $1B + $1.5B | Two blocks separate | **$1B PENALTY / $1.5B REFUNDS** | Clean, no extra motion |
| S52 | 14:50–15:05 | Adobe legal case | DOJ/FTC Adobe complaint evidence | Hard cut to filing | **2024** / verified fee claim | Cold documentary bed |
| S53 | 15:05–15:15 | “Somebody finally wrote a rule.” | Court / FTC building | Slow push | None | Question cliff; music stops |
| S54 | 15:15–15:35 | Click-to-cancel | FTC rule graphic / signup vs cancel flows | Symmetry diagram | **START = STOP** | Feels like answer |
| S55 | 15:35–15:55 | Rule challenge | Trade-group/court docket evidence | Timeline move toward July 8 | **JUL 8, 2025** | Tension returns |
| S56 | 15:55–16:15 | Rule struck down | Eighth Circuit opinion first page | Locked court PDF; page number/source visible | **VACATED** / `PROCEDURE` later | No courtroom stock |
| S57 | 16:15–16:35 | Missing analysis | Opinion text / highlighted procedural paragraph | Detail zoom only on relevant language | **PROCEDURE** | Music nearly gone |
| S58 | 16:35–16:55 | Paperwork failure | Word “PROCEDURE” → administrative flow | Dissolve into process diagram | **RULE → PROCEDURE → VACATED** | Minimal pulse |
| S59 | 16:55–17:15 | 2026 status | Calendar 2026 + FTC rulemaking page | Present-day pull-back | `FEDERAL RULE STATUS: VERIFY BEFORE RECORDING` | Neutral tone |
| S60 | 17:15–17:35 | What remains legal / enforcement | Subscription UI, state law map, FTC cases | 3-layer composition then clear | `STATE LAWS / ENFORCEMENT / NO ONE-SIZE-FITS-ALL` only if current legal review supports | Tease callback |
| S61 | 17:35–17:55 | Return to gym | **Exact same opening shot** | No new camera move | None | Opening tonal DNA returns; audience recognizes callback |
| S62 | 17:55–18:15 | Member/space contradiction returns | Same room + verified current member figure | Reintroduce one number at a time | **20.8M / 2,896** if using 2025 data | Music strips down |
| S63 | 18:15–18:34 | Old economy: payment linked to delivery | Simple object-for-money diagram | Locked | **PAY → RECEIVE** | Calm |
| S64 | 18:34–18:50 | Subscription severed link | Diagram breaks into recurring payment line | Line continues after service card disappears | **PAYMENT CONTINUES** | Low sustained tone |
| S65 | 18:50–19:02 | $133 gap reframed | $133 returns, now alongside statement | Slow pull back | **THE GAP** + study source | No beat for first second |
| S66 | 19:02–19:10 | Practical audit | Bank statement, cursor scanning twelve months | Slow deterministic scroll | **12 MONTHS** | Room tone / almost no music |
| S67 | 19:10–19:14 | Final thesis | Cursor stops on recurring charge → black | **THE POINT IS THAT IT SHOULD BE A CHOICE.** then cut | Music fully gone; **hard stop**, no outro |

> **Important:** The exact scene boundaries above are editorial cut points. The underlying narration remains the script in `new_story_script.md`. Do not rewrite prose inside the video-engine plan merely to fit a visual duration; align the voice first, then adjust holds/cuts around it.

---

# 4. CHAPTER-BY-CHAPTER DIRECTOR NOTES

## CHAPTER A — 00:00–01:35 — THE MYSTERY

**Retention goal:** create a contradiction before the audience understands the business model.

The opening must not look like a YouTube title card. Start inside a place that feels strangely empty. The viewer's brain should ask: *Where is everybody?* Then the numbers explain why the emptiness matters.

**Do:**
- 6-second visual hold before narration.
- Make the arithmetic discoverable.
- Keep typography sparse.
- Use the $86 → $219 sequence as the second retention spike.

**Do not:**
- flash the title immediately;
- start with a montage;
- show five subscription logos;
- explain the conclusion before “This is the product.”

## CHAPTER B — 01:35–05:35 — BREAKAGE + BALLY

**Retention goal:** teach the economic mechanism, then flip the old explanation.

This chapter can tolerate longer explanatory shots because the viewer is learning a new term and a causal model. The “BREAKAGE” moment is a mandatory visual reset.

Bally is evidence, not villain cosplay. Keep the archive dry. The emotional move is not “Bally bad”; it is “the legal trap created a complaint pathway, so the industry evolved toward softer friction.”

## CHAPTER C — 05:35–06:30 — PLANET FITNESS REVERSAL

This is the first true **business-model reversal**: the contract is removed, but friction does not disappear; it becomes psychological/behavioral.

Visually move from dark/archival to bright/cheap/accessible, then immediately undermine the visual optimism with a tiny recurring-charge UI.

The $10/$120 comparison is a high-value graphic because it converts a small monthly amount into a meaningful annual number without a lecture.

## CHAPTER D — 06:30–10:55 — ADOBE / OWNERSHIP

This chapter needs the largest visual scale shift in the film.

Start with a physical object: boxed software. This instantly communicates ownership in a way a stock office cannot.

The core visual metaphor is:

`BOX / KEY / DISC` → `ACCOUNT / MONTHLY CHARGE`

The revenue chart is evidence of a business-model transformation, not a generic “company growing” chart. Never leave the chart on-screen throughout the paragraph. Move between:

1. owned object
2. historical evidence
3. announcement
4. customer reaction
5. verified revenue/segment data
6. mechanism: ownership changed

The section should feel like discovery, not condemnation.

## CHAPTER E — 10:55–12:05 — STREAMING REBUILDS THE BUNDLE

This is the broadest “everyday life” section.

The audience recognizes the old cable problem. Use that familiarity to make the reversal land:

`ONE BUNDLE` → `MANY SUBSCRIPTIONS` → `SIMILAR TOTAL`

Do not pretend every survey measures the same thing. Pick one current source/methodology and label it. The editorial point survives even when the exact survey number changes.

## CHAPTER F — 12:05–15:15 — AMAZON / ILIAD / $2.5B

This is the strongest evidence section.

Change visual language to **interface + primary documents**.

The cancellation flow itself is the visual argument. Recreate the hierarchy without over-explaining. The viewer should feel how many decisions stand between them and “cancel.”

“ILIAD” must be one of the quietest frames in the film.

Then the $2.5B settlement should be one of the most visually authoritative frames: one number, one source/date, no decorative background noise.

## CHAPTER G — 15:15–17:35 — CLICK-TO-CANCEL / PROCEDURE

Make the rule look like the solution.

Then remove it because of the procedural court holding.

Do not dramatize the legal holding with gavels/judges/angry courtroom stock. The court document is more powerful because it is real.

The “PROCEDURE” reveal should feel frustrating precisely because it is mundane.

## CHAPTER H — 17:35–19:14 — CALLBACK / PRACTICAL PAYOFF

The opening frame returns unchanged.

**This is the point of the entire film:** the picture did not need to change because the audience changed. They now understand what the empty gym means.

The practical action is deliberately mundane: scan 12 months of statements. This keeps the ending useful rather than theatrical.

The final 4 seconds must not have:

- outro narration
- subscribe CTA
- “thanks for watching”
- end-screen voice
- logo flourish
- trailer sting

Hard stop.

---

# 5. AUDIO MAP

## 00:00–01:35
Room tone / fluorescent hum. Minimal pulse only after the contradiction is established.

## 01:35–05:35
Low documentary bed. Remove or thin the bed at **BREAKAGE** and before the Bally reversal.

## 05:35–06:30
Slight tension lift, then make the $10/$120 comparison dry and analytical.

## 06:30–10:55
Broader, more expensive-sounding investigative bed. One clear lift around the verified Adobe revenue consequence.

## 10:55–12:05
Reset. Slightly more rhythmic to support the stacking subscription cards.

## 12:05–15:15
Colder investigative texture. Drop the bed for **ILIAD** and **$2.5 BILLION**.

## 15:15–17:35
Sparse legal tension. Silence/room tone around **PROCEDURE**.

## 17:35–19:14
Return to opening tonal DNA, then strip layers away. Final 10–15 seconds: voice + near-silence.

### SFX rules

Only use sound effects that explain physical action:

- cursor click
- page turn
- card/charge stack
- subtle UI confirm
- restrained impact on a number reveal

Never:

- whoosh every cut
- bass boom every number
- trailer riser under every paragraph
- keyboard typing for generic office footage
- fake “glitch” for legal evidence

---

# 6. TEXT + GRAPHIC PACKAGE

## Mandatory hero cards

1. `THIS IS THE PRODUCT.`
2. `BREAKAGE`
3. `THE CONTRACT WAS THE WRONG TOOL`
4. `OWNED → RENTED`
5. `THE BUNDLE`
6. `ILIAD`
7. `$2.5 BILLION`
8. `PROCEDURE`
9. final thesis: `THE POINT IS THAT IT SHOULD BE A CHOICE.`

## Mandatory evidence treatments

Every evidence shot should include enough source/date context to prevent the frame from becoming an unattributed claim.

Examples:

`FTC — SEP 25, 2025`  
`SEC — ADOBE FY2023 10-K`  
`EIGHTH CIRCUIT — JUL 8, 2025`  
`C+R RESEARCH — SUBSCRIPTION STUDY`

## Graphic restraint

One graphic at a time. Never show a chart + six logos + subtitle + source/date at equal size.

---

# 7. ASSET MANIFEST — WHAT MUST EXIST BEFORE RENDER

## Hero / anchor assets

- `planet-fitness-empty-4am-wide`
- `planet-fitness-exterior-day`
- `planet-fitness-floor-plan-or-space-diagram`
- `bank-statement-recurring-charge-ui`
- `subscriptions-86-vs-219`
- `breakage-black-card`
- `gift-card-dormant-balance`
- `bally-1990s-storefront`
- `bally-contract-document`
- `bally-regulatory-evidence`
- `adobe-photoshop-cs6-box`
- `adobe-license-key-disc`
- `adobe-creative-cloud-announcement-2013`
- `adobe-forum-reaction-collage`
- `adobe-revenue-data-card`
- `cable-bill-2007`
- `early-netflix-archive`
- `streaming-service-stack`
- `amazon-prime-enrollment-recreation`
- `amazon-prime-cancel-flow-recreation`
- `amazon-ftc-complaint-evidence`
- `iliad-black-card`
- `iliad-book`
- `amazon-settlement-ftc-document`
- `adobe-doj-complaint`
- `ftc-click-to-cancel-rule-document`
- `eighth-circuit-opinion-first-page`
- `2026-ftc-negative-option-rulemaking-page`
- `final-bank-statement-audit`

## Asset rules

Each asset must have a stable ID and provenance:

`asset_id, filename, source_type, source_url/source_reference, authenticity, allowed_use, date, aspect_ratio, visual_role`

For generated recreations, label them **RECREATION**, never present them as authentic screenshots.

---

# 8. DIRECTOR-PLAN JSON CONTRACT

The eventual `director-plan.json` should be derivable from this document without creative reinterpretation.

```json
{
  "episode": {
    "id": "real-return-01-company-sells-nothing",
    "runtime": "19:14",
    "mode": "longform-documentary",
    "source_script": "new_story_script.md",
    "retention_strategy": "heatmap-informed-positioned-devices"
  },
  "scenes": [
    {
      "id": "S01",
      "start": 0.0,
      "end": 6.0,
      "viewer_question": "Why is this gym empty?",
      "reward": "mystery",
      "primary_visual": "planet-fitness-empty-4am-wide",
      "motion": "LOCKED",
      "text": [],
      "transition_in": "cut",
      "transition_out": "cut",
      "music": "room-tone",
      "sfx": [],
      "evidence": "establishing",
      "asset_ids": ["planet-fitness-empty-4am-wide"]
    }
  ]
}
```

For every scene, `viewer_question`, `reward`, `evidence`, and `asset_ids` are required. A scene without a reason to exist should be removed rather than padded.

---

# 9. QC GATES FOR THIS EPISODE

## Story gate

- [ ] Hook establishes contradiction before title/explanation.
- [ ] BREAKAGE lands at the designed retention peak.
- [ ] Bally reversal is understandable without moralizing.
- [ ] Adobe section changes the mental model from price to ownership.
- [ ] Streaming section provides a recognizable everyday-life reversal.
- [ ] Amazon section supplies the strongest primary evidence.
- [ ] Click-to-cancel section creates a solution, then removes it.
- [ ] Ending changes the meaning of the opening frame.

## Visual gate

- [ ] No generic B-roll for consequential sentences.
- [ ] No constant Ken Burns movement.
- [ ] No equal-weight information piles.
- [ ] Primary evidence beats decorative assets.
- [ ] Screens/UI are legible on desktop and mobile.
- [ ] Legal/financial documents are held long enough to inspect.
- [ ] Same opening gym frame returns at 17:35.

## Audio gate

- [ ] Voice is always intelligible.
- [ ] Music never competes with evidence narration.
- [ ] Silence is preserved before major reveals.
- [ ] Final 10–15s is nearly dry.

## Factual gate

- [ ] Every number has a source in the fact-check appendix.
- [ ] Current Planet Fitness member/club figures are updated.
- [ ] Adobe metric definitions are consistent.
- [ ] Streaming survey methodology is stated.
- [ ] Amazon settlement amounts/date match FTC primary source.
- [ ] Eighth Circuit holding is described as procedural, not a consumer-policy endorsement.
- [ ] 2026 federal click-to-cancel status is rechecked immediately before publishing.

## Retention gate

- [ ] No unexplained lecture plateau longer than ~45–60s without an evidence/visual reset.
- [ ] Major chapters enter with a visual world change.
- [ ] At least one meaningful reward per 20–60s region.
- [ ] Late-video ending is not padded with CTA/outro.

---

# 10. REVISION PRIORITY IF THE FIRST RENDER IS WEAK

Fix in this order:

**1. Story / narration** — if the question or payoff is weak.  
**2. Evidence** — if the claim is interesting but not shown.  
**3. Scene order** — if a strong idea arrives too late.  
**4. Visual specificity** — replace wallpaper with concrete action/document/UI.  
**5. Rhythm** — compress dead explanations, lengthen important evidence.  
**6. Typography** — remove clutter; strengthen only decisive words.  
**7. Sound** — simplify before adding.  
**8. Motion** — last, not first.

Do **not** respond to a low retention section by adding arbitrary cuts. The `yt_engine` plan explicitly warns that the current corpus is still too thin to turn all language effects into rules; the correct response is evidence-driven iteration, not fake precision.

---

# 11. FINAL EDITORIAL STANDARD

The finished video should feel like a strong human documentary editor assembled it from evidence:

- one idea per frame;
- one meaningful visual change per beat;
- evidence when evidence exists;
- silence when silence makes the line land;
- motion only when motion clarifies meaning;
- charts only when relationships matter;
- logos only when the company/entity matters;
- recreated UI only when interface behavior is part of the evidence;
- no generic AI montage;
- no constant text animation;
- no fake excitement;
- no outro after the final sentence.

The core editorial equation for this episode is:

**MYSTERY → MECHANISM → REVERSAL → OWNERSHIP → BUNDLE → DARK PATTERN → LAW → CALLBACK → CHOICE**

That arc, not the number of visual effects, is what the renderer must protect.

---

## SOURCES / RESEARCH REFERENCE

- R4Flutter/yt_engine `PLAN.md` — intelligence architecture, retention/heatmap approach, current confidence limits.
- R4Flutter/yt_engine `new_story_script.md` — canonical 19:14 narration, retention device map, voice direction, chapter timings.
- R4Flutter/video_engine `prompt/editing-director-19m.md` — long-form directing rules, evidence hierarchy, motion vocabulary, anti-AI editing rules.
- R4Flutter/video_engine `docs/pipeline.html` — pipeline order from VIRALFORGE intelligence through render/master/QC.
- Planet Fitness 2025 10-K, SEC — current 20.8M members / 2,896 clubs and business model details.
- C+R Research — $86 estimated vs $219 itemized subscription spending; forgetfulness findings.
- Adobe 2023 10-K / SEC — Creative Cloud / Digital Media revenue definitions and values.
- FTC, Sept. 25, 2025 — Amazon $2.5B Prime settlement and required cancellation/enrollment changes.
- Eighth Circuit, July 8, 2025 — click-to-cancel rule vacatur and procedural holding.
- FTC Negative Option Rule page, updated 2026 — current rulemaking/status reference.
- Deloitte Digital Media Trends 2025/2026 — streaming subscription counts and spend methodology.
- Morgan Stanley 2026 streaming survey — current broader service-count context.
