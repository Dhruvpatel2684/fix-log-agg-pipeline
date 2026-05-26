"""Tests for the graph reachability analysis system.

Validates correct strongly connected component decomposition,
condensation DAG construction, and inter-component reachability.
"""
import json
import os

OUTPUT_DIR = "/app/runtime/output"


def load_json(filename):
    """Load a JSON output file from the output directory."""
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "r") as f:
        return json.load(f)


class TestOutputStructure:
    """Structural tests verifying output files exist with correct format."""

    def test_output_directory_exists(self):
        """The output directory must exist after analysis runs."""
        assert os.path.isdir(OUTPUT_DIR), (
            f"Output directory {OUTPUT_DIR} was not created"
        )

    def test_all_report_files_generated(self):
        """All required report files must be present."""
        for fname in ["components.json", "condensation.json", "summary.json"]:
            path = os.path.join(OUTPUT_DIR, fname)
            assert os.path.isfile(path), f"Expected output file {fname} not found"

    def test_summary_schema(self):
        """Summary must contain all required aggregate fields."""
        summary = load_json("summary.json")
        for field in ["total_nodes", "total_edges", "total_components",
                      "multi_node_components", "condensation_edges",
                      "largest_component_size"]:
            assert field in summary, f"Missing field '{field}' in summary"

    def test_components_schema(self):
        """Components report must have correct structure."""
        report = load_json("components.json")
        assert "total_components" in report
        assert "components" in report
        assert isinstance(report["components"], list)
        if report["components"]:
            comp = report["components"][0]
            assert "id" in comp
            assert "nodes" in comp
            assert "size" in comp


class TestEdgeInclusion:
    """Tests verifying all configured subsystem edges are processed."""

    def test_total_edge_count(self):
        """All edges from configured categories must be included."""
        summary = load_json("summary.json")
        assert summary["total_edges"] == 20, (
            f"Expected 20 edges from all categories, got {summary['total_edges']}"
        )

    def test_total_node_count(self):
        """All nodes across all subsystems must be present."""
        summary = load_json("summary.json")
        assert summary["total_nodes"] == 13, (
            f"Expected 13 nodes, got {summary['total_nodes']}"
        )


class TestStrongConnectivity:
    """Tests verifying correct strongly connected component decomposition.

    In a directed graph, a strongly connected component (SCC) is a maximal
    subset of nodes where EVERY pair has a directed path in BOTH directions.
    This is distinct from weak connectivity which ignores edge direction.
    """

    def test_component_count(self):
        """The graph must decompose into exactly 7 strongly connected components."""
        report = load_json("components.json")
        assert report["total_components"] == 7, (
            f"Expected 7 SCCs, got {report['total_components']}. "
            "A single large component suggests undirected traversal."
        )

    def test_mutual_reachability_cycle(self):
        """auth-service, cache-layer, user-db form a directed cycle (SCC).

        auth-service -> user-db -> cache-layer -> auth-service creates
        mutual reachability among all three nodes.
        """
        report = load_json("components.json")
        expected_scc = {"auth-service", "cache-layer", "user-db"}
        found = False
        for comp in report["components"]:
            if set(comp["nodes"]) == expected_scc:
                found = True
                break
        assert found, (
            f"Expected SCC containing {expected_scc} not found. "
            "These nodes form a directed cycle."
        )

    def test_bidirectional_pair(self):
        """order-service and payment-service form a 2-node SCC.

        order-service -> payment-service -> order-service creates
        a bidirectional pair.
        """
        report = load_json("components.json")
        expected_scc = {"order-service", "payment-service"}
        found = False
        for comp in report["components"]:
            if set(comp["nodes"]) == expected_scc:
                found = True
                break
        assert found, (
            f"Expected SCC containing {expected_scc} not found. "
            "These nodes have edges in both directions."
        )

    def test_singleton_no_incoming_cycle(self):
        """api-gateway has no incoming edges, so it must be a singleton SCC."""
        report = load_json("components.json")
        found = False
        for comp in report["components"]:
            if comp["nodes"] == ["api-gateway"]:
                found = True
                break
        assert found, (
            "api-gateway should be a singleton SCC (no incoming edges, "
            "so no other node can reach it via directed paths)"
        )

    def test_largest_component_size(self):
        """The largest SCC should have 3 nodes (not 11 or 13)."""
        summary = load_json("summary.json")
        assert summary["largest_component_size"] == 3, (
            f"Expected largest SCC size 3, got {summary['largest_component_size']}. "
            "A size of 11+ suggests the algorithm is finding weakly connected "
            "components instead of strongly connected components."
        )


class TestCondensationDAG:
    """Tests verifying correct condensation DAG construction.

    The condensation DAG has an edge from SCC-X to SCC-Y when there exists
    an original edge from some node in SCC-X to some node in SCC-Y.
    """

    def test_condensation_edge_count(self):
        """The condensation DAG must have exactly 8 edges."""
        report = load_json("condensation.json")
        assert report["total_edges"] == 8, (
            f"Expected 8 condensation edges, got {report['total_edges']}"
        )

    def test_condensation_has_edges(self):
        """With 7 SCCs, the condensation must have inter-component edges."""
        report = load_json("condensation.json")
        assert len(report["edges"]) > 0, (
            "Condensation has no edges. With multiple SCCs there must be "
            "inter-component dependencies."
        )

    def test_condensation_is_acyclic(self):
        """The condensation must be a DAG (no cycles between components)."""
        report = load_json("condensation.json")
        # Build adjacency and check for cycles via DFS
        adj = {}
        for edge in report["edges"]:
            adj.setdefault(edge["source"], set()).add(edge["target"])

        # Cycle detection using DFS coloring
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in adj}
        for node in list(adj.keys()):
            # Add targets that might not be sources
            for t in adj.get(node, set()):
                if t not in color:
                    color[t] = WHITE

        has_cycle = False
        def dfs(node):
            nonlocal has_cycle
            color[node] = GRAY
            for neighbor in adj.get(node, set()):
                if color.get(neighbor, WHITE) == GRAY:
                    has_cycle = True
                    return
                if color.get(neighbor, WHITE) == WHITE:
                    dfs(neighbor)
            color[node] = BLACK

        for node in list(color.keys()):
            if color[node] == WHITE:
                dfs(node)
        assert not has_cycle, "Condensation contains a cycle — it should be a DAG"


class TestMultiNodeComponents:
    """Tests verifying the count of non-trivial components."""

    def test_multi_node_component_count(self):
        """There should be exactly 5 SCCs with more than one node."""
        summary = load_json("summary.json")
        assert summary["multi_node_components"] == 5, (
            f"Expected 5 multi-node SCCs, got {summary['multi_node_components']}"
        )
