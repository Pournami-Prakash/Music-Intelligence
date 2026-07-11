"""Pydantic request body schemas for POST endpoints."""

from typing import Optional
from pydantic import BaseModel, Field


class ArtistsBatchBody(BaseModel):
    artists: list[str] = Field(default_factory=list, max_length=50)


class GroupBlendBody(BaseModel):
    artists: list[str] = Field(default_factory=list, max_length=6)


class ForensicsBody(BaseModel):
    playlist_url: str = ""
    tracks: list[str] = Field(default_factory=list)


class SoundtrackGiftBody(BaseModel):
    prompt: str = ""
