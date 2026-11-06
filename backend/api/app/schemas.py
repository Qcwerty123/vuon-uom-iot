"""Kiểu dữ liệu API. JSON dùng camelCase (đặc tả §10.1)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Api(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class LoginIn(Api):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class RefreshIn(Api):
    refresh_token: str = Field(min_length=10, max_length=200)


class UserOut(Api):
    id: int
    username: str
    full_name: str | None = None
    email: str | None = None
    role: str
    status: str
    telegram_chat_id: str | None = None


class TokenOut(Api):
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserOut


class MePatch(Api):
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=120)
    telegram_chat_id: str | None = Field(default=None, max_length=40)


class PasswordIn(Api):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class DeviceOut(Api):
    id: int
    device_code: str
    type: str
    name: str
    zone_id: int | None = None
    status: str
    online: bool
    hw_version: str | None = None
    fw_version: str | None = None
    last_seen_at: datetime | None = None
    first_seen_at: datetime | None = None
    current_config_version: int
    note: str | None = None
    permission: str | None = None  # quyền của người đang gọi: VIEW / CONTROL


class DeviceCreate(Api):
    type: Literal["CONTROLLER", "CAMERA"]
    name: str = Field(min_length=1, max_length=120)
    zone_id: int | None = None
    hw_version: str | None = Field(default=None, max_length=30)


class DevicePatch(Api):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    zone_id: int | None = None
    note: str | None = Field(default=None, max_length=1000)


class ReasonIn(Api):
    reason: str = Field(min_length=1, max_length=200)


class DecommissionIn(ReasonIn):
    confirm: str


class ProvisionOut(Api):
    device_code: str
    secret: str
    garden_code: str
    mqtt_host: str
    mqtt_port: int
    upload_url: str
    note: str = "Secret chỉ hiển thị một lần. Chép vào secrets.h rồi nạp firmware."


class AssignmentIn(Api):
    user_id: int
    permission: Literal["VIEW", "CONTROL"] = "VIEW"


class AssignmentOut(Api):
    user_id: int
    username: str
    role: str
    permission: str


class HistoryOut(Api):
    from_status: str | None
    to_status: str
    reason: str | None
    actor_id: int | None
    at: datetime
