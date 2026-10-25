"""Model-service transport; no model implementation is distributed here."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request


class ModelClient:
    def __init__(self, endpoint, token=None, timeout=10):
        if not endpoint:
            raise ValueError("Set --endpoint or DEEPSIGNAL_ENDPOINT")
        self.url = endpoint.rstrip("/") + "/v1/decide"
        self.token = token if token is not None else os.environ.get("HF_TOKEN")
        self.timeout = timeout

    def decide(self, context, frames):
        if len(frames) != 3:
            raise ValueError("Exactly three chronological camera frames are required")
        body = {
            **context,
            "frames": [base64.b64encode(f).decode("ascii") for f in frames],
        }
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            self.url, data=json.dumps(body).encode(), headers=headers
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise RuntimeError(
                    "Model access denied; obtain approval and set HF_TOKEN"
                ) from None
            raise RuntimeError(f"Model service returned HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError(
                "Model service unavailable or request timed out"
            ) from None
        if result.get("error") or result.get("choice") not in context["legal_actions"]:
            raise RuntimeError("Model service did not return a legal action")
        version = result.get("model_version")
        if not version:
            raise RuntimeError("Model service must identify its model_version")
        return {
            "choice": result["choice"],
            "model_version": version,
            "round_trip_ms": (time.perf_counter() - started) * 1000,
        }
