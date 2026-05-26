"""Report generator for graph analysis results.

Produces structured JSON output files containing:
- components.json: SCC decomposition with node membership
- condensation.json: DAG edges and reachability between components
- summary.json: aggregate statistics
"""
import json
import os
import configparser


class Reporter:
    """Generates output reports from graph analysis results."""

    def __init__(self, config_path):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._output_dir = self._config.get("graph", "output_dir")

    def generate_reports(self, components, dag_edges, dag_reachability,
                         edge_count, base_dir):
        """Generate all output reports."""
        output_path = os.path.join(base_dir, self._output_dir)
        os.makedirs(output_path, exist_ok=True)

        self._write_components(components, output_path)
        self._write_condensation(dag_edges, dag_reachability, output_path)
        self._write_summary(components, dag_edges, edge_count, output_path)

    def _write_components(self, components, output_path):
        """Write SCC decomposition report."""
        report = {
            "total_components": len(components),
            "components": [
                {"id": comp_id, "nodes": nodes, "size": len(nodes)}
                for comp_id, nodes in sorted(components.items())
            ],
        }
        filepath = os.path.join(output_path, "components.json")
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

    def _write_condensation(self, dag_edges, dag_reachability, output_path):
        """Write condensation DAG report."""
        edges_list = [
            {"source": src, "target": tgt}
            for src, tgt in sorted(dag_edges)
        ]
        report = {
            "total_edges": len(edges_list),
            "edges": edges_list,
            "reachability": dag_reachability,
        }
        filepath = os.path.join(output_path, "condensation.json")
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

    def _write_summary(self, components, dag_edges, edge_count, output_path):
        """Write summary statistics."""
        total_nodes = sum(len(nodes) for nodes in components.values())
        multi_node_components = [
            comp_id for comp_id, nodes in components.items() if len(nodes) > 1
        ]

        summary = {
            "total_nodes": total_nodes,
            "total_edges": edge_count,
            "total_components": len(components),
            "multi_node_components": len(multi_node_components),
            "condensation_edges": len(dag_edges),
            "largest_component_size": max(
                len(nodes) for nodes in components.values()
            ) if components else 0,
        }
        filepath = os.path.join(output_path, "summary.json")
        with open(filepath, "w") as f:
            json.dump(summary, f, indent=2)
