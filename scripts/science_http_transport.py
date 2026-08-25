from __future__ import annotations

import urllib.error
import urllib.request

import acquire_science_candidates as base


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Return redirect responses to the caller instead of following them implicitly."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class NoRedirectUrllibTransport(base.UrllibTransport):
    """HTTP transport that makes redirects explicit acquisition evidence.

    Provider acquisition is request-identity sensitive. An automatic redirect would
    create an unrecorded HTTP response and silently change the effective endpoint.
    This transport therefore disables automatic redirect following. A redirect is
    returned as an HTTP result and the acquisition layer fails closed while retaining
    its response body in attempt-level custody.
    """

    redirect_policy = "FAIL_CLOSED_NO_AUTO_FOLLOW"

    def __init__(
        self,
        *,
        user_agent: str = base.DEFAULT_USER_AGENT,
        timeout_seconds: float = 60.0,
    ) -> None:
        super().__init__(user_agent=user_agent, timeout_seconds=timeout_seconds)
        self._opener = urllib.request.build_opener(_NoRedirectHandler())

    def fetch(self, url: str) -> base.HttpResult:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                return base.HttpResult(
                    status=int(response.status),
                    headers={k.lower(): v for k, v in response.headers.items()},
                    body=response.read(),
                )
        except urllib.error.HTTPError as exc:
            return base.HttpResult(
                status=int(exc.code),
                headers={k.lower(): v for k, v in exc.headers.items()},
                body=exc.read(),
            )
