"""Định dạng lỗi chung của API (đặc tả §10.1): {code, message, details, traceId}."""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("api")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status, self.code, self.message, self.details = status, code, message, details or {}


def not_found(what: str = "Không tìm thấy") -> ApiError:
    return ApiError(404, "NOT_FOUND", what)


def forbidden(msg: str = "Không đủ quyền") -> ApiError:
    return ApiError(403, "FORBIDDEN", msg)


def _body(code: str, message: str, details: dict | None = None) -> dict:
    return {"code": code, "message": message, "details": details or {}, "traceId": uuid.uuid4().hex[:12]}


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(_r: Request, e: ApiError):
        return JSONResponse(_body(e.code, e.message, e.details), status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def _val(_r: Request, e: RequestValidationError):
        errs = [{"field": ".".join(str(x) for x in er["loc"][1:]), "message": er["msg"]} for er in e.errors()]
        return JSONResponse(_body("VALIDATION_ERROR", "Dữ liệu không hợp lệ", {"errors": errs}), status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_r: Request, e: StarletteHTTPException):
        code = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(e.status_code, "ERROR")
        return JSONResponse(_body(code, str(e.detail)), status_code=e.status_code)

    @app.exception_handler(Exception)
    async def _any(_r: Request, e: Exception):
        body = _body("INTERNAL_ERROR", "Lỗi máy chủ")
        log.exception("Lỗi không xử lý được (traceId=%s)", body["traceId"])
        return JSONResponse(body, status_code=500)
