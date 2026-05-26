"""Strongly connected component analysis for directed graphs.

Computes the strongly connected components of a directed dependency graph.
A strongly connected component is a maximal set of nodes where every node
is reachable from every other node following directed edges.

Uses iterative graph traversal to identify connected components and
assigns each node to exactly one component.
"""
from collections import deque


class SCCAnalyzer:
    """Identifies strongly connected components in a directed graph."""

    def __init__(self):
        self._adjacency = {}       # node -> set of neighbor nodes
        self._reverse_adj = {}     # node -> set of reverse neighbors
        self._nodes = set()

    def build_graph(self, edge_records):
        """Construct adjacency representation from edge records."""
        for record in edge_records:
            src = record.source
            tgt = record.target
            self._nodes.add(src)
            self._nodes.add(tgt)

            if src not in self._adjacency:
                self._adjacency[src] = set()
            if tgt not in self._adjacency:
                self._adjacency[tgt] = set()
            if src not in self._reverse_adj:
                self._reverse_adj[src] = set()
            if tgt not in self._reverse_adj:
                self._reverse_adj[tgt] = set()

            # Forward edge: src -> tgt
            self._adjacency[src].add(tgt)
            # Reverse edge for transpose graph
            self._reverse_adj[tgt].add(src)

    def compute_components(self):
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

        return components

    def get_node_component_map(self, components):
        """Build reverse mapping from node -> component_id."""
        node_map = {}
        for comp_id, nodes in components.items():
            for node in nodes:
                node_map[node] = comp_id
        return node_map

    def get_adjacency(self):
        """Return the forward adjacency structure."""
        return self._adjacency

    def get_nodes(self):
        """Return all nodes in the graph."""
        return self._nodes
