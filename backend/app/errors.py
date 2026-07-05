from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus


@dataclass
class ApiError(Exception):
    code: str
    message: str
    status: HTTPStatus
