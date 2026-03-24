from __future__ import annotations

import logging

import requests


class HttpClient:
    def __init__(self, base_url: str, auth: tuple[str, str] | None = None, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.timeout = timeout
        self.session = requests.Session()

    def request(self, method: str, path: str, *, auth: tuple[str, str] | None = None, **kwargs):
        url = f"{self.base_url}{path}"
        response = self.session.request(
            method=method,
            url=url,
            auth=auth or self.auth,
            timeout=kwargs.pop("timeout", self.timeout),
            **kwargs,
        )
        logging.info("%s %s -> %s", method.upper(), url, response.status_code)
        return response
