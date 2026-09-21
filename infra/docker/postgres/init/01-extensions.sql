-- Runs once, when the postgres data volume is first initialised.
-- The migrations create the same extensions with IF NOT EXISTS; this only makes
-- a fresh local database usable before the first migration.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
-- pgvector (user_preference.taste_vector, optional in docs/02-erd.md) is NOT part
-- of the postgis/postgis image. Swap the image for one that bundles both if needed.
