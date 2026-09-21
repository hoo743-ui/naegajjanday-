from __future__ import annotations

from app.core.config import Settings
from app.infra.analytics.base import EventTracker, NoopTracker


def build_tracker(settings: Settings) -> EventTracker:
    name = settings.analytics_provider
    if name == "ga4" and settings.ga4_measurement_id and settings.ga4_api_secret:
        from app.infra.analytics.ga4 import GA4Tracker

        return GA4Tracker(settings.ga4_measurement_id, settings.ga4_api_secret)
    if name == "posthog" and settings.posthog_api_key:
        from app.infra.analytics.posthog import PostHogTracker

        return PostHogTracker(settings.posthog_api_key, settings.posthog_host)
    if name == "mixpanel" and settings.mixpanel_token:
        from app.infra.analytics.mixpanel import MixpanelTracker

        return MixpanelTracker(settings.mixpanel_token)
    return NoopTracker()
