# hackernews-scrape

Scrape [Hacker News](https://news.ycombinator.com/) data into postgresql database.

Asyncio mostly taken from [https://github.com/ashish01/hn-data-dumps]

## "Online" Index Alter

```sql
CREATE INDEX ON items ("type");
```

## Full text search

[https://blog.crunchydata.com/blog/postgres-full-text-search-a-search-engine-in-a-database]

```
hackernews=# ALTER TABLE items ADD COLUMN ts_title tsvector
    GENERATED ALWAYS AS (to_tsvector('english', title)) STORED;
ALTER TABLE
Time: 767391.958 ms (12:47.392)

hackernews=# CREATE INDEX ts_title_idx ON items USING GIN (ts_title) WITH (timescaledb.transaction_per_chunk);
CREATE INDEX
Time: 194921.790 ms (03:14.922)
```

Let's see it in action

```sql
SELECT DISTINCT(title), ts_rank_cd(ts_title, query) AS rank
FROM items, to_tsquery('ride & hailing') query
WHERE query @@ ts_title
ORDER BY rank DESC;

 Startup bets S.F. needs app to hail scooter-riding valets
 Distracted Driving and the Risks of Ride-Hailing Services Like Uber
 Hollande Calls Uber’s Ride-Hailing Service Illegal Amid Protests
(3 rows)

Time: 101.588 ms
```


Without score index

```sql
 Limit  (cost=1519840.48..1519841.63 rows=10 width=91)
   ->  Gather Merge  (cost=1519840.48..1800523.86 rows=2440725 width=91)
         Workers Planned: 1
         ->  Sort  (cost=1518840.47..1524942.29 rows=2440725 width=91)
               Sort Key: _hyper_1_690_chunk.score DESC
               ->  Result  (cost=82.21..1466097.28 rows=2440725 width=91)
                     ->  Parallel Append  (cost=82.21..1435588.22 rows=2440725 width=63)
                           ->  Parallel Bitmap Heap Scan on _hyper_1_690_chunk  (cost=82.21..3422.29 rows=5316 width=67)
                                 Recheck Cond: (type = 'story'::item_type)
                                 Filter: ((by IS NOT NULL) AND (by <> ''::text))
                                 ->  Bitmap Index Scan on _hyper_1_690_chunk_items_type_idx  (cost=0.00..79.96 rows=9302 width=0)
                                       Index Cond: (type = 'story'::item_type)
                           ->  Parallel Bitmap Heap Scan on _hyper_1_691_chunk  (cost=80.39..3476.40 rows=5181 width=67)
                                 Recheck Cond: (type = 'story'::item_type)
                                 Filter: ((by IS NOT NULL) AND (by <> ''::text))
                                 ->  Bitmap Index Scan on _hyper_1_691_chunk_items_type_idx  (cost=0.00..78.19 rows=9067 width=0)
                                       Index Cond: (type = 'story'::item_type)
                           ->  Parallel Bitmap Heap Scan on _hyper_1_532_chunk  (cost=74.13..3084.26 rows=4792 width=66)
                                 Recheck Cond: (type = 'story'::item_type)
                                 Filter: ((by IS NOT NULL) AND (by <> ''::text))
                                 ->  Bitmap Index Scan on _hyper_1_532_chunk_items_type_idx  (cost=0.00..72.10 rows=8401 width=0)
                                       Index Cond: (type = 'story'::item_type)
```

After score index

```
 Limit  (cost=249.33..258.13 rows=10 width=91)
   ->  Result  (cost=249.33..3660168.12 rows=4161039 width=91)
         ->  Merge Append  (cost=249.33..3608155.13 rows=4161039 width=63)
               Sort Key: _hyper_1_1_chunk.score DESC
               ->  Index Scan Backward using _hyper_1_1_chunk_items_score_idx on _hyper_1_1_chunk  (cost=0.14..2.35 rows=1 width=72)
               ->  Index Scan Backward using _hyper_1_2_chunk_items_score_idx on _hyper_1_2_chunk  (cost=0.14..130.32 rows=166 width=60)
               ->  Index Scan Backward using _hyper_1_3_chunk_items_score_idx on _hyper_1_3_chunk  (cost=0.14..2.35 rows=1 width=72)
               ->  Index Scan Backward using _hyper_1_4_chunk_items_score_idx on _hyper_1_4_chunk  (cost=0.13..2.34 rows=1 width=72)
               ->  Index Scan Backward using _hyper_1_5_chunk_items_score_idx on _hyper_1_5_chunk  (cost=0.12..2.34 rows=1 width=72)
               ->  Index Scan Backward using _hyper_1_6_chunk_items_score_idx on _hyper_1_6_chunk  (cost=0.15..311.46 rows=374 width=62)
```

## Sometime CAGG is not as fast as direct index

The CAGG doesn't reduce enough cardinality from the base table.

Time needed to create CAGG

```
hackernews=# CREATE MATERIALIZED VIEW daily_activity
WITH (timescaledb.continuous) AS
SELECT "by",
   time_bucket(INTERVAL '1 day', time) AS bucket,
   COUNT(*) as post_count,
   SUM(score) as score_sum
FROM items
GROUP BY "by", bucket
WITH NO DATA;
CREATE MATERIALIZED VIEW
Time: 310.361 ms
hackernews=# CALL refresh_continuous_aggregate('daily_activity', NULL, NULL);
CALL
Time: 621885.299 ms (10:21.885)
```

```
SELECT "by" AS username, COUNT(*) AS post_count 
FROM items
WHERE "by" IS NOT NULL AND "by" <> ''
GROUP BY "by"
Time: 39837.616 ms (00:39.838)
Finalize GroupAggregate  (cost=702787.30..711756.78 rows=68996 width=17) (actual time=37878.554..38813.192 rows=784911 loops=1)
   Group Key: _hyper_1_731_chunk.by
   ->  Gather Merge  (cost=702787.30..710721.84 rows=68996 width=17) (actual time=37878.488..38534.955 rows=932800 loops=1)
         Workers Planned: 1
         Workers Launched: 1
         ->  Sort  (cost=701787.29..701959.78 rows=68996 width=17) (actual time=35322.879..35536.305 rows=466400 loops=2)
               Sort Key: _hyper_1_731_chunk.by
               Sort Method: external merge  Disk: 16016kB
               Worker 0:  Sort Method: external merge  Disk: 12560kB
               ->  Partial HashAggregate  (cost=695552.05..696242.01 rows=68996 width=17) (actual time=31735.031..34319.749 rows=466400 loops=2)
                     Group Key: _hyper_1_731_chunk.by
                     Batches: 21  Memory Usage: 10297kB  Disk Usage: 228160kB
                     Worker 0:  Batches: 5  Memory Usage: 10289kB  Disk Usage: 77768kB
                     ->  Parallel Append  (cost=0.29..608083.40 rows=17493730 width=9) (actual time=8506.208..26556.649 rows=14869693 loops=2)
                           ->  Parallel Index Only Scan using _hyper_1_731_chunk_items_type_by_idx on _hyper_1_731_chunk  (cost=0.29..1759.81 rows=59917 width=9) (actual time=8220.956..8342.010 rows=101859 loops=1)
                                 Index Cond: (by IS NOT NULL)
                                 Filter: (by <> ''::text)
                                 Rows Removed by Filter: 3347
                                 Heap Fetches: 0
                           ->  Parallel Index Only Scan using _hyper_1_783_chunk_items_type_by_idx on _hyper_1_783_chunk  (cost=0.29..1644.44 rows=56090 width=9) (actual time=3.298..108.567 rows=95353 loops=1)
                                 Index Cond: (by IS NOT NULL)
                                 Filter: (by <> ''::text)
                                 Rows Removed by Filter: 2530
                                 Heap Fetches: 0
                           ->  Parallel Index Only Scan using _hyper_1_787_chunk_items_type_by_idx on _hyper_1_787_chunk  (cost=0.29..1593.90 rows=54242 width=9) (actual time=5.125..134.976 rows=92211 loops=1)
                                 Index Cond: (by IS NOT NULL)
                                 Filter: (by <> ''::text)
                                 Rows Removed by Filter: 2491
                                 Heap Fetches: 0
                           ->  Parallel Index Only Scan using _hyper_1_786_chunk_items_type_by_idx on _hyper_1_786_chunk  (cost=0.29..1553.18 rows=52740 width=9) (actual time=8.713..115.979 rows=89658 loops=1)
                                 Index Cond: (by IS NOT NULL)
                                 Filter: (by <> ''::text)
                                 Rows Removed by Filter: 2525
                                 Heap Fetches: 0
```


```
SELECT "by" as username, SUM(post_count)
FROM daily_activity 
WHERE "by" IS NOT NULL AND "by" <> ''
GROUP BY "by"
Time: 129438.545 ms (02:09.439)

 GroupAggregate  (cost=1313490.54..1313798.98 rows=200 width=41) (actual time=120929.519..128567.247 rows=784911 loops=1)
   Group Key: "*SELECT* 1".by
   ->  Sort  (cost=1313490.54..1313592.52 rows=40792 width=17) (actual time=120929.460..126230.245 rows=15506951 loops=1)
         Sort Key: "*SELECT* 1".by
         Sort Method: external merge  Disk: 463760kB
         ->  Append  (cost=1096100.43..1310366.69 rows=40792 width=17) (actual time=28090.951..65525.685 rows=15506951 loops=1)
               ->  Subquery Scan on "*SELECT* 1"  (cost=1096100.43..1309009.35 rows=40000 width=17) (actual time=28090.950..64187.914 rows=15506951 loops=1)
                     ->  HashAggregate  (cost=1096100.43..1308609.35 rows=40000 width=33) (actual time=28090.941..62609.693 rows=15506951 loops=1)
                           Group Key: _materialized_hypertable_4.by, _materialized_hypertable_4.bucket
                           Planned Partitions: 64  Batches: 4289  Memory Usage: 10393kB  Disk Usage: 781800kB
                           ->  Custom Scan (ChunkAppend) on _materialized_hypertable_4  (cost=0.00..436449.83 rows=15506938 width=26) (actual time=4891.813..18493.357 rows=15506951 loops=1)
                                 Chunks excluded during startup: 0
                                 ->  Seq Scan on _hyper_4_876_chunk  (cost=0.00..6171.94 rows=219292 width=26) (actual time=4891.811..5191.671 rows=219297 loops=1)
                                       Filter: ((by IS NOT NULL) AND (by <> ''::text) AND (bucket < COALESCE(_timescaledb_internal.to_timestamp_without_timezone(_timescaledb_internal.cagg_watermark(4)), '-infinity'::timestamp without time zone)))
                                 ->  Seq Scan on _hyper_4_877_chunk  (cost=0.00..7735.56 rows=274972 width=26) (actual time=1.592..390.062 rows=274978 loops=1)
                                       Filter: ((by IS NOT NULL) AND (by <> ''::text) AND (bucket < COALESCE(_timescaledb_internal.to_timestamp_without_timezone(_timescaledb_internal.cagg_watermark(4)), '-infinity'::timestamp without time zone)))
                                 ->  Seq Scan on _hyper_4_878_chunk  (cost=0.00..10562.06 rows=375696 width=26) (actual time=0.795..486.684 rows=375703 loops=1)
                                       Filter: ((by IS NOT NULL) AND (by <> ''::text) AND (bucket < COALESCE(_timescaledb_internal.to_timestamp_without_timezone(_timescaledb_internal.cagg_watermark(4)), '-infinity'::timestamp without time zone)))
                                 ->  Seq Scan on _hyper_4_879_chunk  (cost=0.00..10145.42 rows=360964 width=26) (actual time=1.145..452.807 rows=360971 loops=1)
                                       Filter: ((by IS NOT NULL) AND (by <> ''::text) AND (bucket < COALESCE(_timescaledb_internal.to_timestamp_without_timezone(_timescaledb_internal.cagg_watermark(4)), '-infinity'::timestamp without time zone)))
                                 ->  Seq Scan on _hyper_4_880_chunk  (cost=0.00..1863.90 rows=66241 width=25) (actual time=1.214..228.519 rows=66245 loops=1)
                                       Filter: ((by IS NOT NULL) AND (by <> ''::text) AND (bucket < COALESCE(_timescaledb_internal.to_timestamp_without_timezone(_timescaledb_internal.cagg_watermark(4)), '-infinity'::timestamp without time zone)))
                                 ->  Seq Scan on _hyper_4_881_chunk  (cost=0.00..9679.92 rows=344239 width=26) (actual time=1.018..310.931 rows=344246 loops=1)
                                       Filter: ((by IS NOT NULL) AND (by <> ''::text) AND (bucket < COALESCE(_timescaledb_internal.to_timestamp_without_timezone(_timescaledb_internal.cagg_watermark(4)), '-infinity'::timestamp without time zone)))
```

Index only scan is fast because it doesn't need to read the actual row

On SUM(post_count) we need to check the actual row

```
SELECT date_trunc('month', time) AS date, count(*) AS post_count
FROM items 
WHERE time > '2000-01-01' -- Don't include "deleted" item which have timestamp 1970 by default
GROUP BY date
ORDER BY date ASC

 Sort  (cost=961405.59..961407.18 rows=635 width=16)
   Sort Key: (date_trunc('month'::text, items."time"))
   ->  HashAggregate  (cost=961368.09..961376.03 rows=635 width=16)
         Group Key: (date_trunc('month'::text, items."time"))
         ->  Custom Scan (ChunkAppend) on items  (cost=0.14..731681.95 rows=30624818 width=8)
               Order: date_trunc('month'::text, items."time")
               ->  Index Only Scan Backward using _hyper_1_1_chunk_items_time_idx on _hyper_1_1_chunk  (cost=0.14..3.15 rows=46 width=8)
                     Index Cond: ("time" > '2000-01-01 00:00:00'::timestamp without time zone)
               ->  Index Only Scan Backward using _hyper_1_3_chunk_items_time_idx on _hyper_1_3_chunk  (cost=0.14..2.56 rows=13 width=8)
                     Index Cond: ("time" > '2000-01-01 00:00:00'::timestamp without time zone)
               ->  Index Only Scan Backward using _hyper_1_4_chunk_items_time_idx on _hyper_1_4_chunk  (cost=0.13..2.36 rows=2 width=8)
                     Index Cond: ("time" > '2000-01-01 00:00:00'::timestamp without time zone)
               ->  Index Only Scan Backward using _hyper_1_5_chunk_items_time_idx on _hyper_1_5_chunk  (cost=0.12..1.24 rows=1 width=8)
                     Index Cond: ("time" > '2000-01-01 00:00:00'::timestamp without time zone)
               ->  Index Only Scan Backward using _hyper_1_2_chunk_items_time_idx on _hyper_1_2_chunk  (cost=0.15..7.16 rows=275 width=8)
                     Index Cond: ("time" > '2000-01-01 00:00:00'::timestamp without time zone)
               ->  Index Only Scan Backward using _hyper_1_6_chunk_items_time_idx on _hyper_1_6_chunk  (cost=0.28..27.82 rows=1197 width=8)
                     Index Cond: ("time" > '2000-01-01 00:00:00'::timestamp without time zone)
               ->  Index Only Scan Backward using _hyper_1_7_chunk_items_time_idx on _hyper_1_7_chunk  (cost=0.28..27.81 rows=1196 width=8)
                     Index Cond: ("time" > '2000-01-01 00:00:00'::timestamp without time zone)
               ->  Index Only Scan Backward using _hyper_1_8_chunk_items_time_idx on _hyper_1_8_chunk  (cost=0.28..31.71 rows=1419 width=8)
                     Index Cond: ("time" > '2000-01-01 00:00:00'::timestamp without time zone)
               ->  Index Only Scan Backward using _hyper_1_9_chunk_items_time_idx on _hyper_1_9_chunk  (cost=0.28..29.38 rows=1286 width=8)
                     Index Cond: ("time" > '2000-01-01 00:00:00'::timestamp without time zone)

SELECT date_trunc('month', bucket) AS date, SUM(post_count)
FROM daily_activity 
WHERE bucket > '2000-01-01' -- Don't include "deleted" item which have timestamp 1970 by default
GROUP BY date
ORDER BY date ASC

GroupAggregate  (cost=1313978.47..1314287.40 rows=200 width=40)
   Group Key: (date_trunc('month'::text, "*SELECT* 1".bucket))
   ->  Sort  (cost=1313978.47..1314080.44 rows=40791 width=16)
         Sort Key: (date_trunc('month'::text, "*SELECT* 1".bucket))
         ->  Result  (cost=1096076.21..1310854.70 rows=40791 width=16)
               ->  Append  (cost=1096076.21..1310344.81 rows=40791 width=16)
                     ->  Subquery Scan on "*SELECT* 1"  (cost=1096076.21..1308984.91 rows=40000 width=16)
                           ->  HashAggregate  (cost=1096076.21..1308584.91 rows=40000 width=33)
                                 Group Key: _materialized_hypertable_4.by, _materialized_hypertable_4.bucket
                                 Planned Partitions: 64
                                 ->  Custom Scan (ChunkAppend) on _materialized_hypertable_4  (cost=0.00..436426.28 rows=15506922 width=26)
                                       Chunks excluded during startup: 0
                                       ->  Seq Scan on _hyper_4_904_chunk  (cost=0.00..7260.12 rows=257956 width=26)
                                             Filter: ((bucket > '2000-01-01 00:00:00'::timestamp without time zone) AND (bucket < COALESCE(_timescaledb_internal.to_timestamp_without_timezone(_timescaledb_internal.cagg_watermark(4)), '-infinity'::timestamp without time zone)))
                                       ->  Seq Scan on _hyper_4_887_chunk  (cost=0.00..8330.30 rows=296265 width=26)
                                             Filter: ((bucket > '2000-01-01 00:00:00'::timestamp without time zone) AND (bucket < COALESCE(_timescaledb_internal.to_timestamp_without_timezone(_timescaledb_internal.cagg_watermark(4)), '-infinity'::timestamp without time zone)))
                                       ->  Seq Scan on _hyper_4_886_chunk  (cost=0.00..7747.46 rows=275323 width=26)
                                             Filter: ((bucket > '2000-01-01 00:00:00'::timestamp without time zone) AND (bucket < COALESCE(_timescaledb_internal.to_timestamp_without_timezone(_timescaledb_internal.cagg_watermark(4)), '-infinity'::timestamp without time zone)))
                                       ->  Seq Scan on _hyper_4_951_chunk  (cost=0.00..371.30 rows=13215 width=25)
                                             Filter: ((bucket > '2000-01-01 00:00:00'::timestamp without time zone) AND (bucket < COALESCE(_timescaledb_internal.to_timestamp_without_timezone(_timescaledb_internal.cagg_watermark(4)), '-infinity'::timestamp without time zone)))
```