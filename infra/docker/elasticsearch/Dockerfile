# Elasticsearch single node for local development with the Korean (nori)
# analysis plugin that docs/02-erd.md section 5 relies on.
# Keep ES_VERSION in line with the elasticsearch client pinned in apps/api (8.x).
ARG ES_VERSION=8.15.3
FROM docker.elastic.co/elasticsearch/elasticsearch:${ES_VERSION}

RUN bin/elasticsearch-plugin install --batch analysis-nori
