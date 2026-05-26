# Graph Reachability Analyzer — Debugging Task

## Overview

A directed graph analysis system processes dependency edges between service nodes across multiple subsystems. It decomposes the graph into strongly connected components (SCCs), builds the condensation DAG, and computes inter-component reachability to identify dependency clusters and their hierarchical relationships.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **No external dependencies**: Uses Python standard library only

## Processing Stages

1. **Parsing** — Reads JSONL edge definition files from `/app/runtime/data/` and filters by configured node categories (comma-separated list in config).

2. **Graph Construction** — Builds a directed adjacency representation including both forward and reverse (transpose) edge structures.

3. **SCC Decomposition** — Identifies strongly connected components: maximal subsets where every node can reach every other node via directed paths. A correct SCC algorithm (e.g., Kosaraju's or Tarjan's) requires considering edge direction — two nodes are in the same SCC only if there exists a directed path from A to B AND a directed path from B to A. The algorithm configuration is in `[analysis.scc]`.

4. **Condensation** — Contracts each SCC into a single super-node and builds the resulting DAG. An edge exists from component X to component Y in the condensation when the original graph has an edge from some node in X to some node in Y (where X ≠ Y). The condensation preserves the dependency direction of the original graph.

5. **Reachability** — Computes which components can reach which other components through the condensation DAG.

6. **Reporting** — Generates output files with deterministic ordering. When edges share timestamps, ordering uses subsystem then sequence number as tiebreakers.

## Problem

The system is producing incorrect output:

- The component decomposition appears to merge nodes that should be in separate components
- Some subsystem edges are missing from the analysis
- The condensation DAG structure does not match expected inter-component relationships
- Output ordering may be non-deterministic across subsystems

## Expected Correct Output

When functioning correctly, the system should:

- Process edges from ALL four configured categories (service, database, cache, queue)
- Identify 7 strongly connected components with correct node membership
- Produce a condensation DAG with 8 inter-component edges
- Have no cycles in the condensation (it must be a proper DAG)
- Identify 5 multi-node components and a largest component size of 3

## Output Schema

### `/app/runtime/output/components.json`
| Field | Type | Description |
|-------|------|-------------|
| `total_components` | int | Number of SCCs found |
| `components` | list | Array of component objects |
| `components[].id` | str | Component identifier (SCC-N) |
| `components[].nodes` | list | Sorted list of node names in this SCC |
| `components[].size` | int | Number of nodes in this SCC |

### `/app/runtime/output/condensation.json`
| Field | Type | Description |
|-------|------|-------------|
| `total_edges` | int | Number of edges in the condensation DAG |
| `edges` | list | Array of edge objects |
| `edges[].source` | str | Source component ID |
| `edges[].target` | str | Target component ID |
| `reachability` | dict | Component ID -> list of reachable component IDs |

### `/app/runtime/output/summary.json`
| Field | Type | Description |
|-------|------|-------------|
| `total_nodes` | int | Total nodes in the graph |
| `total_edges` | int | Total edges processed |
| `total_components` | int | Number of SCCs |
| `multi_node_components` | int | SCCs with more than one node |
| `condensation_edges` | int | Edges in the condensation DAG |
| `largest_component_size` | int | Size of the largest SCC |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/config.ini` | Configuration: categories, algorithm settings, output format |
| `/app/runtime/graph_parser.py` | Parses JSONL edge files with category filtering |
| `/app/runtime/scc_analyzer.py` | Computes strongly connected components |
| `/app/runtime/condensation.py` | Builds condensation DAG and computes reachability |
| `/app/runtime/reporter.py` | Generates structured output reports |
| `/app/runtime/run_analysis.py` | Entry point orchestrating all stages |
| `/app/runtime/data/services.jsonl` | Service dependency edges |
| `/app/runtime/data/databases.jsonl` | Database replication edges |
| `/app/runtime/data/queues.jsonl` | Message queue edges |

## Your Task

Identify and fix defects in the runtime source files under `/app/runtime/`. The system should correctly decompose the directed graph into strongly connected components, build an accurate condensation DAG, and produce deterministic output including all configured edge categories.
