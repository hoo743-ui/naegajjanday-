"""Solver factory (doc 06 §6.2): ≤ 9 nodes → Held-Karp, larger → OR-Tools, else NN + 2-opt."""

from __future__ import annotations

from app.domain.routing import ortools_solver
from app.domain.routing.held_karp import HeldKarpOptimizer
from app.domain.routing.problem import RouteOptimizer, RouteProblem, RouteSolution
from app.domain.routing.two_opt import TwoOptOptimizer

HELD_KARP_MAX_NODES = 9


def choose_optimizer(node_count: int, *, ortools_available: bool | None = None) -> RouteOptimizer:
    """`node_count` includes the origin."""
    if node_count <= HELD_KARP_MAX_NODES:
        return HeldKarpOptimizer()
    available = ortools_solver.ORTOOLS_AVAILABLE if ortools_available is None else ortools_available
    if available:
        try:
            return ortools_solver.OrToolsOptimizer()
        except ortools_solver.OrToolsUnavailableError:
            pass
    return TwoOptOptimizer()


def optimize(problem: RouteProblem) -> RouteSolution:
    solver = choose_optimizer(problem.n + 1)
    try:
        return solver.solve(problem)
    except ortools_solver.OrToolsUnavailableError:  # timeout / no solution → heuristic fallback
        return TwoOptOptimizer().solve(problem)
