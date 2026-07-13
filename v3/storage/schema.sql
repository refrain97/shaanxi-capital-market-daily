PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('RUNNING', 'PASS', 'FAIL')),
  dataset_count INTEGER NOT NULL DEFAULT 0,
  event_count INTEGER NOT NULL DEFAULT 0,
  note TEXT
);

CREATE TABLE IF NOT EXISTS raw_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  dataset TEXT NOT NULL,
  source_path TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  data_as_of TEXT,
  captured_at TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  UNIQUE(dataset, content_sha256)
);

CREATE TABLE IF NOT EXISTS entities (
  entity_id TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  canonical_name TEXT NOT NULL,
  region TEXT,
  status TEXT,
  attributes_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_name TEXT,
  url TEXT,
  title TEXT,
  published_at TEXT,
  fetched_at TEXT,
  source_quality TEXT,
  attributes_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  event_key TEXT NOT NULL UNIQUE,
  channel TEXT NOT NULL,
  event_type TEXT NOT NULL,
  primary_entity_id TEXT REFERENCES entities(entity_id),
  title TEXT NOT NULL,
  summary TEXT,
  published_at TEXT,
  discovered_at TEXT,
  deadline_at TEXT,
  event_status TEXT,
  novelty_status TEXT,
  quality_status TEXT,
  payload_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_versions (
  event_id TEXT NOT NULL REFERENCES events(event_id),
  payload_hash TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY(event_id, payload_hash)
);

CREATE TABLE IF NOT EXISTS event_sources (
  event_id TEXT NOT NULL REFERENCES events(event_id),
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  relation_type TEXT NOT NULL DEFAULT 'evidence',
  PRIMARY KEY(event_id, source_id)
);

CREATE TABLE IF NOT EXISTS event_timeline (
  timeline_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id),
  occurred_at TEXT,
  label TEXT NOT NULL,
  stage_after TEXT,
  source_ids_json TEXT NOT NULL DEFAULT '[]',
  UNIQUE(event_id, occurred_at, label)
);

CREATE TABLE IF NOT EXISTS event_candidates (
  candidate_id TEXT PRIMARY KEY,
  channel TEXT NOT NULL,
  primary_entity_id TEXT REFERENCES entities(entity_id),
  event_key_seed TEXT NOT NULL,
  title TEXT NOT NULL,
  published_at TEXT,
  rm_category TEXT,
  rm_subcategory TEXT,
  business_priority TEXT,
  novelty_status TEXT NOT NULL,
  normalization_status TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_sources (
  candidate_id TEXT NOT NULL REFERENCES event_candidates(candidate_id),
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  PRIMARY KEY(candidate_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_events_channel_published ON events(channel, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_entity_published ON events(primary_entity_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_deadline ON events(deadline_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_dataset ON raw_snapshots(dataset, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_candidates_channel_status ON event_candidates(channel, normalization_status);
