"""Retry with waiting intervals for outside services (Decision 32).

Schedule: try now, then retry after 2 s, 5 s and 10 s. Only *temporary* failures
(network errors, timeouts, rate limits, server errors) are retried. Mistakes in the
request, bad API keys or exhausted credits fail immediately, because retrying can't fix them.
"""

import logging
import time
from typing import Callable, TypeVar

T = TypeVar("T")
log = logging.getLogger("civi.retry")

RETRY_DELAYS_SECONDS = (2, 5, 10)


class TemporaryServiceError(Exception):
    """A failure that may succeed if tried again later."""


class PermanentServiceError(Exception):
    """A failure that will not be fixed by retrying (bad request, bad key, no credits)."""


def with_retries(
    call: Callable[[], T],
    what: str,
    delays: tuple[float, ...] = RETRY_DELAYS_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run `call`, retrying TemporaryServiceError on the schedule. Raises the last error if all fail."""
    attempt = 0
    while True:
        try:
            return call()
        except TemporaryServiceError as exc:
            if attempt >= len(delays):
                log.warning("%s failed after %d attempts: %s", what, attempt + 1, exc)
                raise
            wait = delays[attempt]
            attempt += 1
            log.info("%s failed (%s); retry %d in %ss", what, exc, attempt, wait)
            sleep(wait)
