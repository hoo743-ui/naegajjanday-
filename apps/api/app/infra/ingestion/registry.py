"""Provider factory. Keys come from settings; a missing key raises ProviderNotConfiguredError."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.infra.ingestion.base import PlaceProvider
from app.infra.ingestion.providers.data_go_kr import (
    CITY_PARK_DATASET_URL,
    CITY_PARK_FIELD_MAP,
    DataGoKrProvider,
)
from app.infra.ingestion.providers.file_provider import FileProvider
from app.infra.ingestion.providers.google_places import GooglePlacesProvider
from app.infra.ingestion.providers.kakao_local import KakaoLocalProvider
from app.infra.ingestion.providers.naver_search import NaverSearchProvider
from app.infra.ingestion.providers.tourapi import TourApiProvider

API_PROVIDERS = ("kakao_local", "naver_search", "google_places", "tourapi", "data_go_kr")
ALL_PROVIDERS = ("file", *API_PROVIDERS)


class UnknownProviderError(ValueError):
    pass


def build_provider(name: str, settings: Settings, *, path: Path | None = None) -> PlaceProvider:
    if name == "file":
        if path is None:
            raise UnknownProviderError("file provider needs a path")
        return FileProvider(path)
    if name == "kakao_local":
        return KakaoLocalProvider(settings.kakao_rest_api_key)
    if name == "naver_search":
        return NaverSearchProvider(settings.naver_search_client_id, settings.naver_search_client_secret)
    if name == "google_places":
        return GooglePlacesProvider(settings.google_places_api_key)
    if name == "tourapi":
        return TourApiProvider(settings.tourapi_service_key)
    if name == "data_go_kr":
        return DataGoKrProvider(
            settings.data_go_kr_service_key,
            CITY_PARK_DATASET_URL,
            CITY_PARK_FIELD_MAP,
            is_free=True,
            category_hint=settings.data_go_kr_category_hint,
        )
    raise UnknownProviderError(f"unknown provider '{name}' (known: {', '.join(ALL_PROVIDERS)})")
