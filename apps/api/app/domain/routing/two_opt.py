"""Nearest-Neighbor construction + 2-opt improvement. Dependency-free fallback solver."""

from __future__ import annotations

from app.domain.routing.problem import RouteProblem, RouteSolution, evaluate


class TwoOptOptimizer:
    name = "nn_2opt"

    def __init__(self, max_rounds: int = 50) -> None:
        self._max_rounds = max_rounds

    def solve(self, problem: RouteProblem) -> RouteSolution:
        n = problem.n
        if n == 0:
            return RouteSolution([], 0.0, True, self.name)
        order = self._nearest_neighbor(problem)
        cost, feasible = evaluate(problem, order)
        for _ in range(self._max_rounds):
            improved = False
            for i in range(n - 1):
                for j in range(i + 1, n):
                    cand = order[:i] + order[i : j + 1][::-1] + order[j + 1 :]
                    c, f = evaluate(problem, cand)
                    if (f and not feasible) or (f == feasible and c < cost - 1e-9):
                        order, cost, feasible, improved = cand, c, f, True
            if not improved:
                break
        return RouteSolution(order, cost, feasible, self.name)

    @staticmethod
    def _nearest_neighbor(problem: RouteProblem) -> list[int]:
        n = problem.n
        before: dict[int, set[int]] = {j: set() for j in range(1, n + 1)}
        for a, b in problem.precedence:
            before[b].add(a)
        order: list[int] = []
        visited: set[int] = set()
        prev, clock = 0, 0.0
        while len(order) < n:
            ready = [j for j in range(1, n + 1) if j not in visited and before[j] <= visited]
            if not ready:  # cyclic precedence; ignore it
                ready = [j for j in range(1, n + 1) if j not in visited]
            in_window = [
                j for j in ready if problem.service_start(j, clock + problem.travel[prev][j]) is not None
            ]
            nxt = min(in_window or ready, key=lambda j: problem.travel[prev][j])
            start = problem.service_start(nxt, clock + problem.travel[prev][nxt])
            clock = (start if start is not None else clock + problem.travel[prev][nxt]) + problem.stay[nxt]
            order.append(nxt)
            visited.add(nxt)
            prev = nxt
        return order
