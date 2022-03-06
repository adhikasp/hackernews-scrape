\set ON_ERROR_STOP on

DROP database IF EXISTS hackernews WITH (FORCE);
CREATE database hackernews;
\c hackernews
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Step 1: Define regular table
CREATE TYPE item_type AS ENUM ('comment', 'story');

CREATE TABLE IF NOT EXISTS stories (
    id int,
    "by" text,
    "time" timestamp,
    title text,
    "url" text,
    "text" text,
    "type" text,
    descendants int,
    score int,
    deleted bool,
    dead bool,

    PRIMARY KEY ("time", id)
);
CREATE INDEX ON stories (id);
CREATE INDEX ON stories ("by");

CREATE TABLE IF NOT EXISTS comments (
    id int,
    parent int,
    "by" text,
    "time" timestamp,
    "text" text,
    "type" text,
    score int,
    deleted bool,
    dead bool,

    PRIMARY KEY ("time", id)
);
CREATE INDEX ON comments (id);
CREATE INDEX ON comments (parent);
CREATE INDEX ON comments ("by");


CREATE TABLE IF NOT EXISTS pollopts (
    id int,
    "by" text,
    "time" timestamp,
    "text" text,
    "type" text,
    score int,
    poll int,

    PRIMARY KEY ("time", id)
);
CREATE INDEX ON pollopts (id);
CREATE INDEX ON pollopts (poll);

-- Step 2: Turn into hypertable
-- SELECT create_hypertable('story', 'time', chunk_time_interval => INTERVAL '7 day');
-- SELECT create_hypertable('comments', 'time', chunk_time_interval => INTERVAL '7 day');
