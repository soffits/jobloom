from __future__ import annotations

from ..errors import EXIT_PROVIDER, JobLoomError


def feed_unavailable() -> None:
    raise JobLoomError(
        "No verified open-source Indeed-native personalized For You provider is available.",
        EXIT_PROVIDER,
        "provider_unavailable",
        "Use `jobloom search --site indeed` for anonymous public search; that is not Indeed For You.",
    )
