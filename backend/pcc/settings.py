"""Validated software settings intents. These models never access hardware."""

import unicodedata
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DeviceId = Literal["pulsar_susanto_x", "ajazz_ak820_pro"]
ProfileId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class MouseSettings(StrictModel):
    """Draft bounds only; an adapter must validate its actual supported values."""

    kind: Literal["mouse"]
    dpi: int | None = Field(default=None, ge=1, le=32000)
    polling_rate_hz: int | None = None

    @field_validator("polling_rate_hz")
    @classmethod
    def polling_rate(cls, value: int | None) -> int | None:
        if value is not None and value not in {125, 250, 500, 1000, 2000, 4000, 8000}:
            raise ValueError("Unsupported draft polling rate.")
        return value

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if self.dpi is None and self.polling_rate_hz is None:
            raise ValueError("At least one desired setting is required.")
        return self


class RgbSettings(StrictModel):
    mode: Literal["static"] = "static"
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    brightness_percent: int = Field(ge=0, le=100)


class KeyboardSettings(StrictModel):
    kind: Literal["keyboard"]
    rgb: RgbSettings


SettingsIntent = Annotated[MouseSettings | KeyboardSettings, Field(discriminator="kind")]


class ProfileDraft(StrictModel):
    name: str = Field(min_length=1, max_length=64)
    device_id: DeviceId
    settings: SettingsIntent

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("Use a nonempty printable profile name.")
        return value

    @model_validator(mode="after")
    def matching_device(self) -> Self:
        expected = "mouse" if self.device_id == "pulsar_susanto_x" else "keyboard"
        if self.settings.kind != expected:
            raise ValueError("Settings do not match this device.")
        return self


class SoftwareProfile(ProfileDraft):
    id: ProfileId
    revision: int = Field(ge=1)


class ProfileUpdate(ProfileDraft):
    revision: int = Field(ge=1)


class ProfileDelete(StrictModel):
    revision: int = Field(ge=1)


class ProfileList(StrictModel):
    profiles: list[SoftwareProfile]
