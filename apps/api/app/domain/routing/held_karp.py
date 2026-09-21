"""Exact Held-Karp DP for the open-path TSP with precedence + time windows.

State (visited-mask, last) keeps a Pareto front of (cost, clock) labels: with waiting allowed, the
cheapest partial path is not always the earliest one, so both must survive to stay exact.
O(n²·2ⁿ) states — intended for ≤ 9 nodes.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.routing.problem import RouteProblem, RouteSolution, evaluate

Label = tuple[float, float, tuple[int, ...]]  # cost, clock, path


def _insert(front: list[Label], new: Label) -> None:
    cost, clock, _ = new
    for c, t, _p in front:
        if c <= cost and t <= clock:
            return
    front[:] = [lb for lb in front if not (cost <= lb[0] and clock <= lb[1])]
    front.append(new)


class HeldKarpOptimizer:
    name = "held_karp"

    def solve(self, problem: RouteProblem) -> RouteSolution:
        n = problem.n
        if n == 0:
            return RouteSolution([], 0.0, True, self.name)
        must_precede = [0] * (n + 1)  # bitmask of nodes that must be visited before node j
        for a, b in problem.precedence:
            must_precede[b] |= 1 << (a - 1)

        dp: dict[tuple[int, int], list[Label]] = {}
        for j in range(1, n + 1):
            if must_precede[j]:
                continue
            start = problem.service_start(j, problem.travel[0][j])
            if start is not None:
                dp[(1 << (j - 1), j)] = [(problem.travel[0][j], start + problem.stay[j], (j,))]

        full = (1 << n) - 1
        for mask in range(1, full + 1):
            for last in range(1, n + 1):
                labels = dp.get((mask, last))
                if not labels:
                    continue
                for nxt in range(1, n + 1):
                    bit = 1 << (nxt - 1)
                    if mask & bit or (must_precede[nxt] & ~mask):
                        continue
                    leg = problem.travel[last][nxt]
                    for cost, clock, path in labels:
                        start = problem.service_start(nxt, clock + leg)
                        if start is None:
                            continue
                        front = dp.setdefault((mask | bit, nxt), [])
                        _insert(front, (cost + leg, start + problem.stay[nxt], (*path, nxt)))

        finals = [lb for last in range(1, n + 1) for lb in dp.get((full, last), [])]
        if finals:
            cost, _clock, path = min(finals, key=lambda lb: (lb[0], lb[1]))
            return RouteSolution(list(path), cost, True, self.name)
        # infeasible under the windows: report the precedence-respecting identity order
        order = _topological_identity(n, problem.precedence)
        cost, _ = evaluate(problem, order)
        return RouteSolution(order, cost, False, self.name)


def _topological_identity(n: int, precedence: Sequence[tuple[int, int]]) -> list[int]:
    pairs = list(precedence)
    order: list[int] = []
    remaining = list(range(1, n + 1))
    while remaining:
        for node in remaining:
            if all(a in order for a, b in pairs if b == node):
                order.append(node)
                remaining.remove(node)
                break
        else:  # cyclic constraints — give up on them
            order.extend(remaining)
            break
    return order
