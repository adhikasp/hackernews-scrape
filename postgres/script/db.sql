\set ON_ERROR_STOP on

DROP database IF EXISTS hackernews WITH (FORCE);
CREATE database hackernews;
\c hackernews
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Step 1: Define regular table
CREATE TYPE item_type AS ENUM ('comment', 'story', 'poll', 'pollopt', 'job');

CREATE TABLE IF NOT EXISTS items (
    id int,
    "by" text,
    "time" timestamptz,
    title text,
    "url" text,
    "text" text,
    "type" item_type,
    descendants int,
    parent int,
    score int,
    deleted bool,
    dead bool,
    poll int,

    PRIMARY KEY ("time", id)
);
-- Step 2: Turn into hypertable
SELECT create_hypertable('items', 'time', chunk_time_interval => INTERVAL '7 day');

-- Step 3: Indexes
CREATE INDEX ON items (id) WITH (timescaledb.transaction_per_chunk);
CREATE INDEX ON items ("by") WITH (timescaledb.transaction_per_chunk);
CREATE INDEX ON items ("parent") WITH (timescaledb.transaction_per_chunk);
CREATE INDEX items_score_idx ON items (score) 
    WITH (timescaledb.transaction_per_chunk)
    WHERE "by" IS NOT NULL AND "by" <> '';

ALTER TABLE items ADD COLUMN ts_title tsvector 
    GENERATED ALWAYS AS (to_tsvector('english', title)) STORED;
CREATE INDEX ts_title_idx ON items USING GIN (ts_title) WITH (timescaledb.transaction_per_chunk);


-- Step 4: Continuous aggregate

CREATE MATERIALIZED VIEW daily_activity
WITH (timescaledb.continuous) AS
SELECT "by",
   time_bucket(INTERVAL '1 day', time) AS bucket,
   COUNT(*) as post_count,
   SUM(score) as score_sum
FROM items
WHERE "by" IS NOT NULL AND "by" <> ''
GROUP BY "by", bucket
WITH NO DATA;

CALL refresh_continuous_aggregate('daily_activity', NULL, NULL);

SELECT add_continuous_aggregate_policy('daily_activity',
     end_offset => INTERVAL '1 month',
     schedule_interval => INTERVAL '1 day');
