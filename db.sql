\set ON_ERROR_STOP on

DROP database IF EXISTS hackernews WITH (FORCE);
CREATE database hackernews;
\c hackernews
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Step 1: Define regular table
CREATE TYPE item_type AS ENUM ('comment', 'story', 'pollopts', 'job');

CREATE TABLE IF NOT EXISTS items (
    id int,
    "by" text,
    "time" timestamp,
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
CREATE INDEX ON items (id);
CREATE INDEX ON items ("by");

-- Step 2: Turn into hypertable
SELECT create_hypertable('items', 'time', chunk_time_interval => INTERVAL '7 day');
