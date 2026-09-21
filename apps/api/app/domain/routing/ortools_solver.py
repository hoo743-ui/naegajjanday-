"""Google OR-Tools routing with a time dimension + precedence (doc 06 §6.2). Import is guarded."""

from __future__ import annotations

from typing import Any

from app.domain.routing.problem import RouteProblem, RouteSolution, evaluate

try:  # optional dependency: `uv sync --extra ortools`
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    ORTOOLS_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the environment
    pywrapcp = routing_enums_pb2 = None
    ORTOOLS_AVAILABLE = False

SCALE = 100  # OR-Tools wants integers: minutes → centi-minutes
HORIZON = 72 * 60 * SCALE


class OrToolsUnavailableError(RuntimeError):
    pass


class OrToolsOptimizer:
    name = "ortools"

    def __init__(self, time_limit_ms: int = 300) -> None:
        if not ORTOOLS_AVAILABLE:
            raise OrToolsUnavailableError("ortools is not installed")
        self._time_limit_ms = time_limit_ms

    def solve(self, problem: RouteProblem) -> RouteSolution:
        n = problem.n
        if n == 0:
            return RouteSolution([], 0.0, True, self.name)
        end = n + 1  # dummy end node, zero-cost arcs → open-ended path
        manager = pywrapcp.RoutingIndexManager(n + 2, 1, [0], [end])
        routing = pywrapcp.RoutingModel(manager)

        def travel(i: int, j: int) -> int:
            return 0 if j == end or i == end else round(problem.travel[i][j] * SCALE)

        def cost_cb(from_index: int, to_index: int) -> int:
            return travel(manager.IndexToNode(from_index), manager.IndexToNode(to_index))

        def time_cb(from_index: int, to_index: int) -> int:
            i, j = manager.IndexToNode(from_index), manager.IndexToNode(to_index)
            stay = 0 if i in (0, end) else round(problem.stay[i] * SCALE)
            return stay + travel(i, j)

        routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(cost_cb))
        time_index = routing.RegisterTransitCallback(time_cb)
        routing.AddDimension(time_index, round(problem.max_wait * SCALE), HORIZON, True, "Time")
        time_dim = routing.GetDimensionOrDie("Time")

        for node in range(1, n + 1):
            wins = problem.windows_of(node)
            if wins:  # OR-Tools takes one interval per node: use the hull, verified by evaluate() below
                lo = min(max(0.0, min(w[0] for w in wins)), HORIZON / SCALE)
                hi = min(max(lo, max(w[1] for w in wins)), HORIZON / SCALE)
                time_dim.CumulVar(manager.NodeToIndex(node)).SetRange(round(lo * SCALE), round(hi * SCALE))
        solver = routing.solver()
        for a, b in problem.precedence:
            solver.Add(time_dim.CumulVar(manager.NodeToIndex(a)) <= time_dim.CumulVar(manager.NodeToIndex(b)))

        params: Any = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        params.time_limit.FromMilliseconds(self._time_limit_ms)

        assignment = routing.SolveWithParameters(params)
        if assignment is None:
            raise OrToolsUnavailableError("no solution within the time limit")
        order: list[int] = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node not in (0, end):
                order.append(node)
            index = assignment.Value(routing.NextVar(index))
        cost, feasible = evaluate(problem, order)
        return RouteSolution(order, cost, feasible, self.name)
