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
