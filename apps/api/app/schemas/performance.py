from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class PerformanceVenue(BaseModel):
    name: str
    address: str | None = None
    lat: float
    lng: float
    distance_m: int = Field(description="요청 좌표에서 공연장까지 직선거리")


class PerformanceOut(BaseModel):
    id: str
    title: str
    genre: str | None = None
    venue: PerformanceVenue
    period_from: date | None = None
    period_to: date | None = None
    show_times: list[str] = Field(description='요청한 시간 창 안에 시작하는 회차 ("HH:MM", 현지 시각)')
    runtime_min: int | None = None
    price_text: str | None = Field(default=None, description="KOPIS 가 주는 가격 안내 원문")
    poster_url: str | None = None
    detail_url: str | None = Field(default=None, description="KOPIS 공연 상세 페이지")


class PerformanceList(BaseModel):
    items: list[PerformanceOut] = Field(default_factory=list)
    available: bool = Field(description="false 면 이 환경에 KOPIS 키가 없다 — 웹은 진입점을 숨긴다")
    reason: str | None = Field(default=None, description="available=false 이거나 결과가 빈 이유")
    partial: bool = Field(default=False, description="호출 예산에 걸려 일부만 확인했다 — 잠시 뒤 다시 조회")
    attribution: str = Field(description="이용 조건상 화면에 반드시 표시해야 하는 출처 문구")
