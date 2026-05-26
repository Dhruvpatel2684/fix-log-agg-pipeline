#!/usr/bin/env python3
"""Repair script for graph-reachability-repair task."""
import os
import sys


def patch_graph_parser():
    """Fix: strip whitespace from comma-separated category list."""
    path = "/app/runtime/graph_parser.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'self._allowed_categories = set(raw_categories.split(","))',
        'self._allowed_categories = set(c.strip() for c in raw_categories.split(","))'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_scc_analyzer():
    """Fix: implement Kosaraju's algorithm for true SCCs instead of undirected BFS.

    The buggy code uses BFS traversing both forward and reverse edges,
    which finds weakly connected components. Correct SCC computation
    requires Kosaraju's two-pass algorithm:
    1. DFS on forward graph to get finish order
    2. DFS on reverse graph in reverse finish order
    """
    path = "/app/runtime/scc_analyzer.py"
    with open(path, "r") as f:
        content = f.read()

    # Replace the entire compute_components method
    old = '''    def compute_components(self):
        """Compute strongly connected components.

        Identifies maximal subsets of nodes where mutual reachability holds.
        Two nodes are in the same component if each can reach the other
        through directed paths in the graph.

        Returns a dict mapping component_id -> sorted list of node names.
        """
        # Use iterative BFS to find connected components
        # Visit all reachable nodes from each unvisited starting node
        visited = set()
        components = {}
        component_id = 0

        for start_node in sorted(self._nodes):
            if start_node in visited:
                continue

            # BFS to find all nodes connected to start_node
            component_nodes = set()
            queue = deque([start_node])
            while queue:
                node = queue.popleft()
                if node in component_nodes:
                    continue
                component_nodes.add(node)
                # Explore all connections (both directions for reachability)
                for neighbor in self._adjacency.get(node, set()):
                    if neighbor not in component_nodes:
                        queue.append(neighbor)
                for neighbor in self._reverse_adj.get(node, set()):
                    if neighbor not in component_nodes:
                        queue.append(neighbor)

            visited.update(component_nodes)
            components[f"SCC-{component_id}"] = sorted(component_nodes)
            component_id += 1

        return components'''

    new = '''    def compute_components(self):
        """Compute strongly connected components using Kosaraju's algorithm.

        Pass 1: DFS on forward graph to establish finish ordering.
        Pass 2: DFS on reverse graph in reverse finish order to find SCCs.

        Returns a dict mapping component_id -> sorted list of node names.
        """
        # Pass 1: iterative DFS on forward graph, record finish order
        finish_order = []
        visited = set()

        for start_node in sorted(self._nodes):
            if start_node in visited:
                continue
            stack = [(start_node, False)]
            while stack:
                node, processed = stack.pop()
                if processed:
                    finish_order.append(node)
                    continue
                if node in visited:
                    continue
                visited.add(node)
                stack.append((node, True))
                for neighbor in sorted(self._adjacency.get(node, set())):
                    if neighbor not in visited:
                        stack.append((neighbor, False))

        # Pass 2: DFS on reverse graph in reverse finish order
        visited2 = set()
        components = {}
        component_id = 0

        for node in reversed(finish_order):
            if node in visited2:
                continue
            # DFS on reverse graph from this node
            component_nodes = []
            stack = [node]
            while stack:
                current = stack.pop()
                if current in visited2:
                    continue
                visited2.add(current)
                component_nodes.append(current)
                for neighbor in sorted(self._reverse_adj.get(current, set())):
                    if neighbor not in visited2:
                        stack.append(neighbor)

            components[f"SCC-{component_id}"] = sorted(component_nodes)
            component_id += 1

        return components'''

    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)


def patch_condensation():
    """Fix: correct condensation edge direction (source_comp -> target_comp)."""
    path = "/app/runtime/condensation.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        "edge = (tgt_comp, src_comp)",
        "edge = (src_comp, tgt_comp)"
    )
    with open(path, "w") as f:
        f.write(content)


def patch_run_analysis():
    """Fix: add subsystem to sort key for deterministic edge ordering."""
    path = "/app/runtime/run_analysis.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        "key=lambda e: (e.timestamp, e.seq)",
        "key=lambda e: (e.timestamp, e.subsystem, e.seq)"
    )
    with open(path, "w") as f:
        f.write(content)


def main():
    patch_graph_parser()
    patch_scc_analyzer()
    patch_condensation()
    patch_run_analysis()

    # Re-run with fixed code
    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]
    from runtime.run_analysis import main as run_main
    run_main()


if __name__ == "__main__":
    main()
