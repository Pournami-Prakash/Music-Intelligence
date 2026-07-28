"""Pydantic request body schemas for POST endpoints."""

from typing import Optional
from pydantic import BaseModel, Field


class ArtistsBatchBody(BaseModel):
    artists: list[str] = Field(default_factory=list, max_length=50)


class GroupBlendBody(BaseModel):
    artists: list[str] = Field(default_factory=list, max_length=6)


class ForensicsBody(BaseModel):
    playlist_url: str = Field(default="", max_length=2048)
    tracks: list[str] = Field(default_factory=list, max_length=500)


class PlaylistUrlBody(BaseModel):
    playlist_url: str = Field(default="", max_length=2048)


class SoundtrackGiftBody(BaseModel):
    prompt: str = Field(default="", max_length=500)
