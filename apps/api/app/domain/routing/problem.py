"""Open-path TSP with precedence constraints and time windows (doc 06 §6.1).

Node 0 is the origin; nodes 1..n are stops. The path is open-ended (no return leg).
All times are minutes relative to departure from the origin.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

Window = tuple[float, float]  # allowed ARRIVAL interval [lo, hi]


@dataclass(frozen=True, slots=True)
class RouteProblem:
    travel: Sequence[Sequence[float]]  # (n+1)×(n+1) minutes
    stay: Sequence[float]  # per node, stay[0] == 0
    windows: Sequence[Sequence[Window]] = field(default_factory=tuple)  # per node; empty = unconstrained
    precedence: Sequence[tuple[int, int]] = field(default_factory=tuple)  # (before, after)
    max_wait: float = 45.0

    @property
    def n(self) -> int:
        return len(self.travel) - 1

    def windows_of(self, node: int) -> Sequence[Window]:
        return self.windows[node] if node < len(self.windows) else ()

    def service_start(self, node: int, arrival: float) -> float | None:
        """Earliest feasible start of the visit given the arrival time, or None if infeasible."""
        wins = self.windows_of(node)
        if not wins:
            return arrival
        best: float | None = None
        for lo, hi in wins:
            if arrival > hi:
                continue
            start = max(arrival, lo)
            if start - arrival <= self.max_wait and (best is None or start < best):
                best = start
        return best


@dataclass(frozen=True, slots=True)
class RouteSolution:
    order: list[int]  # visiting order of nodes 1..n
    cost: float  # total travel minutes
    feasible: bool
    solver: str


class RouteOptimizer(Protocol):
    name: str

    def solve(self, problem: RouteProblem) -> RouteSolution: ...


def evaluate(problem: RouteProblem, order: Sequence[int]) -> tuple[float, bool]:
    """Total travel minutes and feasibility (precedence + time windows) of a visiting order."""
    pos = {node: i for i, node in enumerate(order)}
    feasible = all(pos[a] < pos[b] for a, b in problem.precedence if a in pos and b in pos)
    cost, clock, prev = 0.0, 0.0, 0
    for node in order:
        leg = problem.travel[prev][node]
        cost += leg
        start = problem.service_start(node, clock + leg)
        if start is None:
            feasible = False
            start = clock + leg
        clock = start + problem.stay[node]
        prev = node
    return cost, feasible
