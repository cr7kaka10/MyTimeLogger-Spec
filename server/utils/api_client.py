# -*- coding: utf-8 -*-
"""服务端同步 HTTP 客户端。"""

import httpx


class APIClient:
    """封装带认证头的 HTTP 请求，供本地存储层同步到 FastAPI 服务端。"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        sync_config = self.config.get("server_sleep_sync", {})
        self.base_url = sync_config.get("base_url", "http://127.0.0.1:8000").rstrip("/")
        self.auth_token = sync_config.get("auth_token", "")
        self.server_mode = bool(self.config.get("server_mode", False))

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
            headers["X-Auth-Token"] = self.auth_token
        return headers

    def request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.request(
                    method,
                    url,
                    headers=self._headers(),
                    **kwargs,
                )
            response.raise_for_status()
            try:
                return True, response.json()
            except ValueError:
                return True, response.text
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            try:
                data = exc.response.json()
                if isinstance(data, dict) and data.get("detail"):
                    detail = data["detail"]
            except ValueError:
                pass
            return False, f"{exc.response.status_code} {detail}"
        except httpx.RequestError as exc:
            return False, f"网络连接失败: {exc}"

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self.request("DELETE", path, **kwargs)
