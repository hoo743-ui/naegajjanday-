from __future__ import annotations

import itertools
import math
import random

import pytest

from app.domain.models import GeoPoint
from app.domain.routing import ortools_solver
from app.domain.routing.held_karp import HeldKarpOptimizer
from app.domain.routing.optimizer import choose_optimizer, optimize
from app.domain.routing.problem import RouteProblem, evaluate
from app.domain.routing.travel_time import (
    HaversineEstimator,
    KakaoMobilityProvider,
    TravelProviderNotConfiguredError,
    encode_polyline,
    haversine_m,
)
from app.domain.routing.two_opt import TwoOptOptimizer


def random_problem(
    rng: random.Random, n: int, precedence: list[tuple[int, int]] | None = None
) -> RouteProblem:
    pts = [(rng.uniform(0, 30), rng.uniform(0, 30)) for _ in range(n + 1)]
    travel = [[math.dist(a, b) for b in pts] for a in pts]
    return RouteProblem(
        travel=travel, stay=[0.0] + [rng.choice([20.0, 40.0, 60.0])] * n, precedence=precedence or []
    )


def brute_force(problem: RouteProblem) -> float:
    best = math.inf
    for order in itertools.permutations(range(1, problem.n + 1)):
        cost, feasible = evaluate(problem, order)
        if feasible:
            best = min(best, cost)
    return best


class TestHeldKarp:
    @pytest.mark.parametrize("seed", range(12))
    def test_matches_brute_force_on_random_instances(self, seed: int) -> None:
        rng = random.Random(seed)
        problem = random_problem(rng, n=rng.randint(2, 7))
        solution = HeldKarpOptimizer().solve(problem)
        assert solution.feasible
        assert sorted(solution.order) == list(range(1, problem.n + 1))
        assert solution.cost == pytest.approx(brute_force(problem))

    @pytest.mark.parametrize("seed", range(8))
    def test_optimal_under_precedence(self, seed: int) -> None:
        rng = random.Random(100 + seed)
        n = rng.randint(3, 6)
        precedence = [(1, 2), (2, n)]
        problem = random_problem(rng, n, precedence)
        solution = HeldKarpOptimizer().solve(problem)
        pos = {node: i for i, node in enumerate(solution.order)}
        assert all(pos[a] < pos[b] for a, b in precedence)
        assert solution.cost == pytest.approx(brute_force(problem))

    def test_time_windows_force_a_longer_but_feasible_order(self) -> None:
        # nodes on a line: origin 0, A at 10, B at 20. B only accepts arrivals in the first 25 minutes.
        travel = [[0, 10, 20], [10, 0, 10], [20, 10, 0]]
        free = RouteProblem(travel=travel, stay=[0, 30, 30])
        assert HeldKarpOptimizer().solve(free).order == [1, 2]
        windowed = RouteProblem(travel=travel, stay=[0, 30, 30], windows=[[], [], [(0, 25)]])
        solution = HeldKarpOptimizer().solve(windowed)
        assert solution.order == [2, 1] and solution.feasible and solution.cost == 30

    def test_infeasible_windows_are_reported(self) -> None:
        problem = RouteProblem(travel=[[0, 50], [50, 0]], stay=[0, 10], windows=[[], [(0, 5)]])
        solution = HeldKarpOptimizer().solve(problem)
        assert not solution.feasible and solution.order == [1]

    def test_waiting_is_bounded(self) -> None:
        problem = RouteProblem(travel=[[0, 5], [5, 0]], stay=[0, 10], windows=[[], [(120, 200)]], max_wait=45)
        assert not HeldKarpOptimizer().solve(problem).feasible
        assert (
            RouteProblem(problem.travel, problem.stay, problem.windows, max_wait=200).service_start(1, 5)
            == 120
        )


class TestTwoOpt:
    @pytest.mark.parametrize("seed", range(6))
    def test_valid_permutation_respecting_precedence(self, seed: int) -> None:
        rng = random.Random(200 + seed)
        precedence = [(1, 5), (2, 9)]
        problem = random_problem(rng, 11, precedence)
        solution = TwoOptOptimizer().solve(problem)
        assert sorted(solution.order) == list(range(1, 12))
        assert solution.feasible
        assert solution.cost == pytest.approx(evaluate(problem, solution.order)[0])

    def test_not_worse_than_nearest_neighbor_and_close_to_optimal(self) -> None:
        rng = random.Random(3)
        problem = random_problem(rng, 7)
        nn_cost, _ = evaluate(problem, TwoOptOptimizer._nearest_neighbor(problem))
        solution = TwoOptOptimizer().solve(problem)
        assert solution.cost <= nn_cost + 1e-9
        assert solution.cost <= brute_force(problem) * 1.25


class TestFactory:
    def test_small_problems_use_held_karp(self) -> None:
        assert choose_optimizer(9).name == "held_karp"
        assert choose_optimizer(2).name == "held_karp"

    def test_large_problems_use_ortools_or_fall_back(self) -> None:
        assert choose_optimizer(10, ortools_available=False).name == "nn_2opt"
        expected = "ortools" if ortools_solver.ORTOOLS_AVAILABLE else "nn_2opt"
        assert choose_optimizer(10).name == expected

    def test_optimize_large_instance_returns_valid_route(self) -> None:
        problem = random_problem(random.Random(5), 12, [(1, 2)])
        solution = optimize(problem)
        assert sorted(solution.order) == list(range(1, 13))
        assert solution.order.index(1) < solution.order.index(2)


class TestTravelTime:
    def test_haversine_estimator_uses_detour_and_speed(self) -> None:
        a, b = GeoPoint(37.5572, 126.9245), GeoPoint(37.5662, 126.9245)  # ≈ 1 km north
        assert haversine_m(a, b) == pytest.approx(1000, rel=0.01)
        est = HaversineEstimator()
        assert est.estimate(a, b, "walk").minutes == pytest.approx(1.0 * 1.3 / 4.5 * 60, rel=0.01)
        assert est.estimate(a, b, "car").minutes == pytest.approx(1.0 * 1.4 / 22 * 60, rel=0.01)
        assert est.estimate(a, b, "transit").minutes < est.estimate(a, b, "walk").minutes

    def test_http_adapter_needs_a_key(self) -> None:
        with pytest.raises(TravelProviderNotConfiguredError, match="KAKAO_MOBILITY_API_KEY"):
            KakaoMobilityProvider(None)

    def test_polyline_reference_vector(self) -> None:
        pts = [GeoPoint(38.5, -120.2), GeoPoint(40.7, -120.95), GeoPoint(43.252, -126.453)]
        assert encode_polyline(pts) == "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
