"""Condensation DAG builder for strongly connected components.

The condensation of a directed graph is the DAG formed by contracting each
strongly connected component into a single node. Edges in the condensation
represent dependencies between components: if there is an edge from node A
in SCC-X to node B in SCC-Y (where X != Y), then the condensation has an
edge from SCC-X to SCC-Y.
"""


class CondensationBuilder:
    """Builds the condensation DAG from components and original edges."""

    def __init__(self):
        self._dag_edges = set()  # set of (source_scc, target_scc) tuples
        self._dag_adjacency = {}

    def build_condensation(self, components, node_map, adjacency):
        """Build the condensation DAG from the SCC decomposition.

        For each edge (u, v) in the original graph where u and v belong
        to different SCCs, add a corresponding edge in the condensation.
        The condensation edge represents that the source component has
        a dependency on the target component.
        """
        for node, neighbors in adjacency.items():
            src_comp = node_map.get(node)
            if src_comp is None:
                continue
            for neighbor in neighbors:
                tgt_comp = node_map.get(neighbor)
                if tgt_comp is None:
                    continue
                # Only add edges between different components
                if src_comp != tgt_comp:
                    # Record the inter-component dependency
                    edge = (tgt_comp, src_comp)
                    self._dag_edges.add(edge)

        # Build adjacency for the DAG
        for src, tgt in self._dag_edges:
            if src not in self._dag_adjacency:
                self._dag_adjacency[src] = set()
            self._dag_adjacency[src].add(tgt)

        return self._dag_edges

    def get_dag_edges(self):
        """Return all edges in the condensation DAG as (source, target) tuples."""
        return sorted(self._dag_edges)

    def get_dag_adjacency(self):
        """Return the adjacency structure of the condensation DAG."""
        return self._dag_adjacency

    def compute_dag_reachability(self, components):
        """Compute which components can reach which other components in the DAG.

        Returns a dict: component_id -> set of reachable component_ids.
        """
        all_comps = set(components.keys())
        reachability = {}

        for comp in sorted(all_comps):
            # BFS from this component in the DAG
            reachable = set()
            queue = [comp]
            visited = set()
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                if current != comp:
                    reachable.add(current)
                for neighbor in self._dag_adjacency.get(current, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)
            reachability[comp] = sorted(reachable)

        return reachability
