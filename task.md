# Fix Log Aggregation Pipeline - Incremental Compaction Recovery

## Background

You are an on-call engineer at a distributed logging company. The log aggregation
pipeline ingests entries from multiple source nodes via Write-Ahead Log (WAL)
segments and periodically compacts them into a unified, deduplicated, temporally-
ordered output.

## Incident Report

After a recent deployment, the monitoring dashboard is showing several anomalies
in the compaction output:

1. **Temporal ordering violations** - downstream consumers are receiving entries
   out of timestamp order, causing their sliding-window analytics to produce
   incorrect results.

2. **Duplicate entries leaking through** - the deduplication engine is failing
   to catch certain duplicates that appear at exact time window boundaries,
   causing inflated event counts.

3. **Index incompleteness** - the temporal index used for range queries is
   missing entries, causing queries to return incomplete results.

4. **Sequence ID conflicts after recovery** - when the pipeline crashes and
   resumes from a checkpoint, sequence IDs overlap with previously emitted
   entries, causing downstream systems to reject records as duplicates.

## Your Task

Investigate and fix the bugs in the compaction pipeline. The system is located
in `environment/src/` and consists of:

- `models.py` - Core data structures
- `wal_reader.py` - WAL segment loader
- `dedup_engine.py` - Sliding-window deduplication
- `merger.py` - Multi-segment merge into ordered stream
- `temporal_index.py` - Time-based index builder
- `compactor.py` - Orchestrates the compaction pipeline
- `recovery.py` - Crash recovery coordinator

Test fixtures are in `environment/fixtures/` and contain:
- WAL segments from multiple source nodes
- A checkpoint representing a partial compaction that was interrupted

## Invariants That Must Hold

After compaction, ALL of the following must be true:

1. **Temporal monotonicity**: Output entries are ordered by timestamp (non-decreasing)
2. **Dedup completeness**: No duplicate (source_id, payload) pairs within the dedup window (5 seconds, boundaries inclusive)
3. **Index completeness**: The temporal index contains every output entry
4. **Sequence continuity**: After checkpoint recovery, new sequence IDs start above all previously emitted IDs

## Running Tests

```bash
pytest tests/ -v
```
