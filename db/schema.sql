-- VIRALFORGE schema — PLAN.md Section 4

CREATE TABLE IF NOT EXISTS channels (
  channel_id TEXT PRIMARY KEY,
  title TEXT, subs INTEGER, total_views INTEGER, video_count INTEGER,
  country TEXT, niche_tag TEXT,
  median_views_30 REAL,
  uploads_playlist TEXT,
  last_crawled TEXT
);

CREATE TABLE IF NOT EXISTS videos (
  video_id TEXT PRIMARY KEY,
  channel_id TEXT REFERENCES channels(channel_id),
  title TEXT, description TEXT, published_at TEXT,
  duration_sec INTEGER, is_short INTEGER,
  category_id TEXT, tags_json TEXT,
  views INTEGER, likes INTEGER, comments INTEGER,
  outlier_score REAL,
  thumb_path TEXT, crawled_at TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
  video_id TEXT, captured_at TEXT,
  views INTEGER, likes INTEGER, comments INTEGER,
  PRIMARY KEY (video_id, captured_at)
);

CREATE TABLE IF NOT EXISTS transcripts (
  video_id TEXT PRIMARY KEY,
  full_text TEXT, hook_text TEXT,
  words_json TEXT,
  source TEXT
);

CREATE TABLE IF NOT EXISTS heatmaps (
  video_id TEXT PRIMARY KEY,
  points_json TEXT,
  peak_moments_json TEXT, dip_moments_json TEXT
);

CREATE TABLE IF NOT EXISTS video_features (
  video_id TEXT PRIMARY KEY,
  title_len INTEGER, title_word_count INTEGER, title_has_number INTEGER,
  title_number_is_specific INTEGER, title_uppercase_ratio REAL,
  title_formula TEXT,
  hook_archetype TEXT,
  hook_dna_json TEXT,
  hook_promise_sec REAL,
  cuts_per_min REAL, avg_shot_sec REAL,
  thumb_word_count INTEGER, thumb_has_face INTEGER, thumb_face_emotion TEXT,
  thumb_contrast REAL, thumb_saturation REAL,
  topic_cluster INTEGER, embedding BLOB,
  vph_24h REAL, vph_7d REAL
);

CREATE TABLE IF NOT EXISTS my_videos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_path TEXT, props_path TEXT, created_at TEXT,
  score REAL, scorecard_json TEXT, iterations INTEGER,
  published_video_id TEXT,
  actual_ctr REAL, actual_avd_pct REAL, actual_views_72h INTEGER
);

CREATE TABLE IF NOT EXISTS benchmarks (
  niche_tag TEXT, format TEXT, metric TEXT,
  p25 REAL, p50 REAL, p75 REAL, p90 REAL,
  updated_at TEXT,
  PRIMARY KEY (niche_tag, format, metric)
);
-- ---------------------------------------------------------------------------
-- sentences: the alignment training set (miner/alignment.py).
-- One row per spoken sentence, joined to the retention heat at the moment it
-- was spoken. This is what turns the heatmap corpus into a language model of
-- what holds finance viewers. ~300 rows per video; stream it, never load whole.
CREATE TABLE IF NOT EXISTS sentences (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id      TEXT REFERENCES videos(video_id),
  idx           INTEGER,
  t_start       REAL,
  t_end         REAL,
  text          TEXT,
  word_count    INTEGER,
  wpm           REAL,
  -- labels
  heat          REAL,
  heat_delta    REAL,
  heat_z        REAL,
  -- features
  rel_pos       REAL,
  has_dollar    INTEGER,
  has_number    INTEGER,
  number_specific INTEGER,
  has_percent   INTEGER,
  is_question   INTEGER,
  is_contrast   INTEGER,
  is_consequence INTEGER,
  names_person  INTEGER,
  names_org     INTEGER,
  new_entity    INTEGER,
  abstract_subj INTEGER,
  sec_since_entity REAL,
  sec_since_number REAL,
  len_delta     REAL
);
CREATE INDEX IF NOT EXISTS idx_sentences_video ON sentences(video_id);
-- ---------------------------------------------------------------------------
-- hook_library: structured Hook DNA for every mined hook (miner/hooks.py).
-- One row per hook: text + timing + structure + psychology + retention.
-- Retention columns are z-scored WITHIN each video (see hook_retention.py);
-- never compare raw values across videos.
CREATE TABLE IF NOT EXISTS hook_library (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id      TEXT REFERENCES videos(video_id),
  title         TEXT,
  channel       TEXT,
  niche_tag     TEXT,
  outlier_score REAL,
  hook_text     TEXT,
  -- timing
  hook_start    REAL,
  hook_end      REAL,
  word_count    INTEGER,
  duration      REAL,
  wpm           REAL,
  -- structure / psychology (Hook DNA)
  archetype          TEXT,
  opening_device     TEXT,
  curiosity_mechanism TEXT,
  emotional_mechanism TEXT,
  stakes_type        TEXT,
  promise_type       TEXT,
  narrative_structure TEXT,
  -- temporal markers
  first_number_sec    REAL,
  first_entity_sec    REAL,
  first_stakes_sec    REAL,
  first_curiosity_sec REAL,
  promise_sec         REAL,
  -- retention (within-video z)
  retention_1s  REAL, retention_3s  REAL, retention_5s  REAL,
  retention_10s REAL, retention_15s REAL, retention_20s REAL, retention_30s REAL,
  early_retention  REAL,
  retention_slope  REAL,
  retention_drop   REAL,
  retention_recovery REAL,
  peak_retention   REAL,
  peak_sec         REAL,
  volatility       REAL,
  -- scoring / evidence
  hook_score      REAL,
  embedding       BLOB,
  factuality      TEXT,
  analyzed_at     TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_hook_library_video ON hook_library(video_id);
CREATE INDEX IF NOT EXISTS idx_hook_library_score ON hook_library(hook_score DESC);
-- ---------------------------------------------------------------------------
-- hook_generations: the feedback loop. Every generate() call is recorded so
-- published-video performance can later be joined back to the predicted scores
-- (miner/hooks.py record-outcome + feedback/calibrate.py).
CREATE TABLE IF NOT EXISTS hook_generations (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  topic         TEXT,
  mode          TEXT,
  duration_target REAL,
  hooks_json    TEXT,
  generated_at  TEXT,
  selected_hook_text TEXT,
  my_video_id   INTEGER,
  actual_ctr    REAL,
  actual_avd_pct REAL,
  actual_views_72h INTEGER
);
-- ---------------------------------------------------------------------------
-- hook_training_examples: the M4 learning set (miner/hook_learn.py).
-- One row per hook with retention. Every feature is derived deterministically
-- from hook_library + hook_dna_json. Targets are within-video z-scores at the
-- same horizons the generator optimizes. Built by `python -m miner.hooks train
-- --build` and consumed WITHOUT pandas — features are streamed from this table.
CREATE TABLE IF NOT EXISTS hook_training_examples (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id      TEXT REFERENCES videos(video_id),
  channel_id    TEXT,
  channel       TEXT,
  niche_tag     TEXT,
  hook_text     TEXT,
  -- numeric features
  word_count    INTEGER, wpm REAL, hook_duration REAL, outlier_score REAL,
  first_number_sec REAL, first_entity_sec REAL, first_stakes_sec REAL,
  first_curiosity_sec REAL, promise_sec REAL,
  specific_number_count INTEGER, entity_count INTEGER, company_count INTEGER,
  -- categorical features (one-hot encoded at train time)
  opening_device TEXT, curiosity_mechanism TEXT, emotional_mechanism TEXT,
  stakes_type TEXT, promise_type TEXT,
  -- binary features
  open_loop INTEGER, has_question INTEGER, concrete_outcome INTEGER,
  has_number INTEGER, has_dollar INTEGER, has_percent INTEGER, has_date INTEGER,
  number_before_5s INTEGER, entity_before_5s INTEGER, stakes_before_5s INTEGER,
  curiosity_before_5s INTEGER, promise_before_10s INTEGER,
  struct_state INTEGER, struct_contradiction INTEGER, struct_reversal INTEGER,
  struct_question INTEGER, struct_stakes INTEGER, struct_shock INTEGER,
  struct_claim INTEGER, struct_problem INTEGER, struct_consequence INTEGER,
  struct_promise INTEGER, struct_mystery INTEGER, struct_unexpected INTEGER,
  struct_open_loop INTEGER, struct_statement INTEGER,
  -- targets (within-video z, from hook_library retention_*s)
  target_3s REAL, target_5s REAL, target_10s REAL, target_15s REAL, target_30s REAL,
  built_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_training_video ON hook_training_examples(video_id);
CREATE INDEX IF NOT EXISTS idx_training_channel ON hook_training_examples(channel_id);
-- ---------------------------------------------------------------------------
-- learned_patterns: patterns discovered from the corpus (miner/hook_learn.py),
-- NOT manually authored. Manual priors live in PATTERNS (hook_gen.py) and are
-- clearly marked "prior"; rows here are marked LEARNED. Effect = mean retention
-- z of hooks with the feature(s) minus the complement, bootstrapped over videos.
CREATE TABLE IF NOT EXISTS learned_patterns (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  pattern_key   TEXT,             -- human label, e.g. "contradiction + number_before_5s"
  scope         TEXT,             -- GLOBAL / FINANCE / BUSINESS / USER_CHANNEL (hierarchy level)
  feature       TEXT,             -- single feature or combo id
  kind          TEXT,             -- single | interaction
  n_videos      INTEGER,
  n_hooks       INTEGER,
  effect_z      REAL,
  ci95_lo       REAL, ci95_hi REAL,
  robust        INTEGER,
  channel_consistency TEXT,
  confidence    TEXT,             -- INSUFFICIENT DATA / LOW / MEDIUM / HIGH
  best_niche    TEXT,
  best_duration_sec TEXT,
  discovered_at TEXT,
  UNIQUE (pattern_key, scope)
);
