"""Cliente común: Python integrado para Streamlit Cloud o FastAPI remoto."""
import os

import requests


class APIClient:
    def __init__(self):
        self.base_url = os.environ.get("ERP_API_URL", "").rstrip("/")
        if self.base_url:
            self.client = requests.Session()
        else:
            from fastapi.testclient import TestClient
            from erp_backend import app
            # Cada sesión tiene su transporte; nunca se almacenan tokens globales.
            self.client = TestClient(app, raise_server_exceptions=False)

    def request(self, method, path, *, token=None, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if self.base_url:
            kwargs.setdefault("timeout", 30)
        else:
            kwargs.pop("timeout", None)
        url = f"{self.base_url}{path}" if self.base_url else path
        return self.client.request(method, url, headers=headers, **kwargs)
