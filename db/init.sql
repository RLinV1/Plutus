-- Runs once on first Postgres init. Enables pgvector; tables/indexes are created
-- by the app (db.init_db) / ingest worker.
CREATE EXTENSION IF NOT EXISTS vector;
