"""
Service Dependency Graph Module
================================
Represents the directed dependency graph of microservices. Each edge carries
a propagation delay representing the expected time for a failure signal to
propagate from the source service to the target service.

The graph supports reachability queries, shortest path computation, topological
ordering, and strongly connected component detection.
"""

from __future__ import annotations
import heapq
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple


class ServiceNode:
    """Represents a single service in the dependency graph."""

    __slots__ = ("service_id", "metadata", "in_degree", "out_degree")

    def __init__(self, service_id: str, metadata: Optional[Dict] = None):
        self.service_id = service_id
        self.metadata = metadata or {}
        self.in_degree = 0
        self.out_degree = 0

    def __repr__(self) -> str:
        return f"ServiceNode({self.service_id!r})"

    def __eq__(self, other) -> bool:
        if not isinstance(other, ServiceNode):
            return NotImplemented
        return self.service_id == other.service_id

    def __hash__(self) -> int:
        return hash(self.service_id)


class DependencyEdge:
    """Directed edge representing a dependency relationship with propagation delay."""

    __slots__ = ("source", "target", "propagation_delay_ms", "weight", "edge_type")

    def __init__(
        self,
        source: str,
        target: str,
        propagation_delay_ms: float,
        weight: float = 1.0,
        edge_type: str = "dependency",
    ):
        self.source = source
        self.target = target
        self.propagation_delay_ms = propagation_delay_ms
        self.weight = weight
        self.edge_type = edge_type

    def __repr__(self) -> str:
        return (
            f"DependencyEdge({self.source!r} -> {self.target!r}, "
            f"delay={self.propagation_delay_ms}ms)"
        )


class ServiceDependencyGraph:
    """
    Directed graph of service dependencies with propagation delay annotations.

    Supports:
    - Reachability queries (BFS/DFS based)
    - Shortest path with Dijkstra (by delay or by hop count)
    - Topological sort for DAG ordering
    - SCC detection via Tarjan's algorithm
    - Path enumeration between services
    """

    def __init__(self):
        self._adjacency: Dict[str, List[DependencyEdge]] = defaultdict(list)
        self._reverse_adjacency: Dict[str, List[DependencyEdge]] = defaultdict(list)
        self._nodes: Dict[str, ServiceNode] = {}
        self._reachability_cache: Dict[Tuple[str, str], bool] = {}
        self._path_cache: Dict[Tuple[str, str], Optional[List[str]]] = {}
        self._delay_cache: Dict[Tuple[str, str], float] = {}

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return sum(len(edges) for edges in self._adjacency.values())

    def add_service(self, service_id: str, metadata: Optional[Dict] = None) -> None:
        """Register a service node in the graph."""
        if service_id not in self._nodes:
            self._nodes[service_id] = ServiceNode(service_id, metadata)
            self._reachability_cache.clear()
            self._path_cache.clear()
            self._delay_cache.clear()

    def add_dependency(
        self,
        source: str,
        target: str,
        propagation_delay_ms: float,
        weight: float = 1.0,
        edge_type: str = "dependency",
    ) -> None:
        """Add a directed dependency edge from source to target."""
        if source not in self._nodes:
            self.add_service(source)
        if target not in self._nodes:
            self.add_service(target)

        edge = DependencyEdge(source, target, propagation_delay_ms, weight, edge_type)
        self._adjacency[source].append(edge)
        self._reverse_adjacency[target].append(edge)
        self._nodes[source].out_degree += 1
        self._nodes[target].in_degree += 1

        self._reachability_cache.clear()
        self._path_cache.clear()
        self._delay_cache.clear()

    def get_services(self) -> List[str]:
        """Return all service IDs."""
        return list(self._nodes.keys())

    def get_neighbors(self, service_id: str) -> List[str]:
        """Return direct downstream dependencies of a service."""
        return [edge.target for edge in self._adjacency.get(service_id, [])]

    def get_upstream(self, service_id: str) -> List[str]:
        """Return direct upstream dependencies of a service."""
        return [edge.source for edge in self._reverse_adjacency.get(service_id, [])]

    def get_edge(self, source: str, target: str) -> Optional[DependencyEdge]:
        """Get the edge between two directly connected services."""
        for edge in self._adjacency.get(source, []):
            if edge.target == target:
                return edge
        return None

    def is_reachable(self, source: str, target: str) -> bool:
        """
        Check if target is reachable from source via directed edges.
        Uses BFS with caching for performance.
        """
        if source == target:
            return True

        cache_key = (source, target)
        if cache_key in self._reachability_cache:
            return self._reachability_cache[cache_key]

        visited: Set[str] = set()
        queue = deque([source])
        visited.add(source)

        while queue:
            current = queue.popleft()
            for edge in self._adjacency.get(current, []):
                if edge.target == target:
                    self._reachability_cache[cache_key] = True
                    return True
                if edge.target not in visited:
                    visited.add(edge.target)
                    queue.append(edge.target)

        self._reachability_cache[cache_key] = False
        return False

    def shortest_path(self, source: str, target: str) -> Optional[List[str]]:
        """
        Find shortest path (by hop count) from source to target using BFS.
        Returns list of service IDs forming the path, or None if unreachable.
        """
        cache_key = (source, target)
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]

        if source == target:
            return [source]

        visited: Set[str] = {source}
        queue = deque([(source, [source])])

        while queue:
            current, path = queue.popleft()
            for edge in self._adjacency.get(current, []):
                if edge.target == target:
                    result = path + [target]
                    self._path_cache[cache_key] = result
                    return result
                if edge.target not in visited:
                    visited.add(edge.target)
                    queue.append((edge.target, path + [edge.target]))

        self._path_cache[cache_key] = None
        return None

    def minimum_propagation_delay(self, source: str, target: str) -> Optional[float]:
        """
        Compute the minimum total propagation delay from source to target
        using Dijkstra's algorithm on propagation_delay_ms edge weights.
        Returns None if target is unreachable from source.
        """
        cache_key = (source, target)
        if cache_key in self._delay_cache:
            val = self._delay_cache[cache_key]
            return val if val >= 0 else None

        if source == target:
            self._delay_cache[cache_key] = 0.0
            return 0.0

        dist: Dict[str, float] = {source: 0.0}
        heap = [(0.0, source)]

        while heap:
            d, current = heapq.heappop(heap)
            if current == target:
                self._delay_cache[cache_key] = d
                return d
            if d > dist.get(current, float("inf")):
                continue
            for edge in self._adjacency.get(current, []):
                new_dist = d + edge.propagation_delay_ms
                if new_dist < dist.get(edge.target, float("inf")):
                    dist[edge.target] = new_dist
                    heapq.heappush(heap, (new_dist, edge.target))

        self._delay_cache[cache_key] = -1.0
        return None

    def topological_sort(self) -> Optional[List[str]]:
        """
        Return topological ordering of services, or None if graph has cycles.
        Uses Kahn's algorithm.
        """
        in_degree = defaultdict(int)
        for node in self._nodes:
            in_degree[node] = 0
        for edges in self._adjacency.values():
            for edge in edges:
                in_degree[edge.target] += 1

        queue = deque([n for n, d in in_degree.items() if d == 0])
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for edge in self._adjacency.get(node, []):
                in_degree[edge.target] -= 1
                if in_degree[edge.target] == 0:
                    queue.append(edge.target)

        if len(result) != len(self._nodes):
            return None
        return result

    def find_all_paths(
        self, source: str, target: str, max_depth: int = 10
    ) -> List[List[str]]:
        """
        Enumerate all simple paths from source to target up to max_depth.
        Returns list of paths, each path is a list of service IDs.
        """
        if source not in self._nodes or target not in self._nodes:
            return []

        all_paths: List[List[str]] = []
        stack: List[Tuple[str, List[str], Set[str]]] = [
            (source, [source], {source})
        ]

        while stack:
            current, path, visited = stack.pop()
            if len(path) > max_depth:
                continue
            for edge in self._adjacency.get(current, []):
                if edge.target == target:
                    all_paths.append(path + [target])
                elif edge.target not in visited:
                    new_visited = visited | {edge.target}
                    stack.append((edge.target, path + [edge.target], new_visited))

        return all_paths

    def compute_path_delay(self, path: List[str]) -> float:
        """Compute total propagation delay along a given path."""
        total = 0.0
        for i in range(len(path) - 1):
            edge = self.get_edge(path[i], path[i + 1])
            if edge is None:
                return float("inf")
            total += edge.propagation_delay_ms
        return total

    def get_strongly_connected_components(self) -> List[Set[str]]:
        """Find SCCs using Tarjan's algorithm."""
        index_counter = [0]
        stack: List[str] = []
        lowlink: Dict[str, int] = {}
        index: Dict[str, int] = {}
        on_stack: Set[str] = set()
        sccs: List[Set[str]] = []

        def strongconnect(v: str):
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)

            for edge in self._adjacency.get(v, []):
                w = edge.target
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])

            if lowlink[v] == index[v]:
                component: Set[str] = set()
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    component.add(w)
                    if w == v:
                        break
                sccs.append(component)

        for node in self._nodes:
            if node not in index:
                strongconnect(node)

        return sccs

    def subgraph(self, services: Set[str]) -> "ServiceDependencyGraph":
        """Extract a subgraph containing only the specified services."""
        sub = ServiceDependencyGraph()
        for s in services:
            if s in self._nodes:
                sub.add_service(s, self._nodes[s].metadata)
        for s in services:
            for edge in self._adjacency.get(s, []):
                if edge.target in services:
                    sub.add_dependency(
                        edge.source,
                        edge.target,
                        edge.propagation_delay_ms,
                        edge.weight,
                        edge.edge_type,
                    )
        return sub

    def reverse(self) -> "ServiceDependencyGraph":
        """Return a new graph with all edges reversed."""
        rev = ServiceDependencyGraph()
        for s in self._nodes:
            rev.add_service(s, self._nodes[s].metadata)
        for edges in self._adjacency.values():
            for edge in edges:
                rev.add_dependency(
                    edge.target,
                    edge.source,
                    edge.propagation_delay_ms,
                    edge.weight,
                    edge.edge_type,
                )
        return rev

    def transitive_closure(self) -> Dict[str, Set[str]]:
        """Compute the transitive closure (all reachable sets) via BFS per node."""
        closure: Dict[str, Set[str]] = {}
        for node in self._nodes:
            reachable: Set[str] = set()
            queue = deque([node])
            visited = {node}
            while queue:
                current = queue.popleft()
                for edge in self._adjacency.get(current, []):
                    if edge.target not in visited:
                        visited.add(edge.target)
                        reachable.add(edge.target)
                        queue.append(edge.target)
            closure[node] = reachable
        return closure

    def degree_centrality(self) -> Dict[str, float]:
        """Compute normalized degree centrality for each service."""
        n = len(self._nodes)
        if n <= 1:
            return {s: 0.0 for s in self._nodes}
        centrality = {}
        for s in self._nodes:
            total_degree = len(self._adjacency.get(s, [])) + len(
                self._reverse_adjacency.get(s, [])
            )
            centrality[s] = total_degree / (2 * (n - 1))
        return centrality

    @classmethod
    def from_dict(cls, data: Dict) -> "ServiceDependencyGraph":
        """
        Build graph from dictionary format:
        {
            "services": ["svc_a", "svc_b", ...],
            "edges": [
                {"source": "svc_a", "target": "svc_b", "propagation_delay_ms": 150},
                ...
            ]
        }
        """
        graph = cls()
        for svc in data.get("services", []):
            if isinstance(svc, dict):
                graph.add_service(svc["id"], svc.get("metadata"))
            else:
                graph.add_service(svc)

        for edge_data in data.get("edges", []):
            graph.add_dependency(
                source=edge_data["source"],
                target=edge_data["target"],
                propagation_delay_ms=edge_data.get("propagation_delay_ms", 100.0),
                weight=edge_data.get("weight", 1.0),
                edge_type=edge_data.get("edge_type", "dependency"),
            )
        return graph

    def to_dict(self) -> Dict:
        """Serialize graph to dictionary format."""
        edges = []
        for edge_list in self._adjacency.values():
            for edge in edge_list:
                edges.append(
                    {
                        "source": edge.source,
                        "target": edge.target,
                        "propagation_delay_ms": edge.propagation_delay_ms,
                        "weight": edge.weight,
                        "edge_type": edge.edge_type,
                    }
                )
        return {"services": list(self._nodes.keys()), "edges": edges}
