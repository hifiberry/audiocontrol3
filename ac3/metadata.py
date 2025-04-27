"""
Metadata handling for AudioControl3
"""
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any, List, Union
import json
import enum


class PlayerState(enum.Enum):
    """
    Player state enumeration
    """
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


@dataclass
class Song:
    """
    Class representing metadata for a song/track
    """
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    track_number: Optional[int] = None
    total_tracks: Optional[int] = None
    duration: Optional[float] = None  # in seconds
    genre: Optional[str] = None
    year: Optional[int] = None
    cover_art_url: Optional[str] = None
    stream_url: Optional[str] = None
    source: Optional[str] = None  # e.g., "spotify", "local", "radio"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """
        Convert song metadata to JSON string
        
        Returns:
            JSON string representation of the song metadata
        """
        # Filter out None values
        result = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(result)


@dataclass
class Player:
    """
    Class representing metadata for a media player
    """
    name: str  # Name of the player (required)
    player_id: Optional[str] = None  # Unique identifier for the player
    type: Optional[str] = None  # Type of player (e.g., "mpd", "spotify", "bluetooth")
    state: Union[PlayerState, str] = PlayerState.UNKNOWN  # Current state (e.g., "playing", "paused", "stopped")
    volume: Optional[int] = None  # Current volume level (0-100)
    muted: Optional[bool] = None  # Whether the player is muted
    capabilities: Optional[List[str]] = None  # Player capabilities (e.g., ["play", "pause", "next"])
    active: Optional[bool] = None  # Whether this player is the currently active one
    position: Optional[float] = None  # Current playback position in seconds
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """
        Convert player metadata to JSON string
        
        Returns:
            JSON string representation of the player metadata
        """
        # Filter out None values
        result = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(result)