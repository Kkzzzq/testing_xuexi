from __future__ import annotations

from urllib.parse import urljoin

import requests
from requests import Response, Session


class HttpClient:
    def __init__(
        self,
        base_url: str,
        auth: tuple[str, str] | None = None,
        timeout: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.auth = auth
        self.timeout = timeout
        self.session: Session = requests.Session()

    def request(self, method: str, path: str, **kwargs) -> Response:
        url = urljoin(self.base_url, path.lstrip("/"))
        kwargs.setdefault("timeout", self.timeout)
        if self.auth and "auth" not in kwargs:
            kwargs["auth"] = self.auth
        return self.session.request(method=method.upper(), url=url, **kwargs)

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
