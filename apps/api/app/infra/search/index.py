"""`places-v{n}` index definition (ERD §5): nori for Korean, edge-ngram for autocomplete."""

from __future__ import annotations

from typing import Any

INDEX_VERSION = 1


def index_name(version: int = INDEX_VERSION) -> str:
    return f"places-v{version}"


PLACES_INDEX: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 1,
        "analysis": {
            "tokenizer": {
                "nori_mixed": {"type": "nori_tokenizer", "decompound_mode": "mixed"},
                "edge_ngram_tok": {
                    "type": "edge_ngram",
                    "min_gram": 1,
                    "max_gram": 20,
                    "token_chars": ["letter", "digit"],
                },
            },
            "analyzer": {
                "korean": {
                    "type": "custom",
                    "tokenizer": "nori_mixed",
                    "filter": ["lowercase", "nori_part_of_speech", "nori_readingform"],
                },
                "autocomplete_index": {
                    "type": "custom",
                    "tokenizer": "edge_ngram_tok",
                    "filter": ["lowercase"],
                },
                "autocomplete_search": {"type": "custom", "tokenizer": "standard", "filter": ["lowercase"]},
            },
        },
    },
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "public_id": {"type": "keyword"},
            "name": {
                "type": "text",
                "analyzer": "korean",
                "fields": {
                    "autocomplete": {
                        "type": "text",
                        "analyzer": "autocomplete_index",
                        "search_analyzer": "autocomplete_search",
                    },
                    "raw": {"type": "keyword"},
                },
            },
            "address": {"type": "text", "analyzer": "korean"},
            "category_code": {"type": "keyword"},
            "course_role": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "region_slug": {"type": "keyword"},
            "location": {"type": "geo_point"},
            "price_per_person": {"type": "integer"},
            "is_free": {"type": "boolean"},
            "bayes_rating": {"type": "float"},
            "sentiment_score": {"type": "float"},
            "popularity": {"type": "float"},
            "status": {"type": "keyword"},
        },
    },
}
