"""Entry point for the graph reachability analysis system.

Orchestrates the full analysis:
1. Parse edge records from data files
2. Build directed graph
3. Compute strongly connected components
4. Build condensation DAG
5. Compute inter-component reachability
6. Generate output reports
"""
import os

from runtime.graph_parser import GraphParser
from runtime.scc_analyzer import SCCAnalyzer
from runtime.condensation import CondensationBuilder
from runtime.reporter import Reporter


def main():
    """Run the graph reachability analysis end-to-end."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.ini")

    # Stage 1: Parse edge records
    parser = GraphParser(config_path)
    edges = parser.parse_all(base_dir)

    # Sort edges for deterministic processing
    edges_sorted = sorted(edges, key=lambda e: (e.timestamp, e.seq))

    # Stage 2: Build directed graph
    analyzer = SCCAnalyzer()
    analyzer.build_graph(edges_sorted)

    # Stage 3: Compute SCCs
    components = analyzer.compute_components()
    node_map = analyzer.get_node_component_map(components)

    # Stage 4: Build condensation DAG
    builder = CondensationBuilder()
    dag_edges = builder.build_condensation(
        components, node_map, analyzer.get_adjacency()
    )

    # Stage 5: Compute DAG reachability
    dag_reachability = builder.compute_dag_reachability(components)

    # Stage 6: Generate reports
    reporter = Reporter(config_path)
    reporter.generate_reports(
        components, dag_edges, dag_reachability,
        len(edges_sorted), base_dir
    )

    print(f"Graph analysis complete. Processed {len(edges_sorted)} edges.")
    print(f"  Nodes: {len(analyzer.get_nodes())}")
    print(f"  Components: {len(components)}")
    print(f"  Condensation edges: {len(dag_edges)}")


if __name__ == "__main__":
    main()
