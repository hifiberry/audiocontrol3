"""
Null Player Controller

This module provides a no-op implementation of PlayerController that does nothing.
It's useful as a fallback or placeholder controller when no real player is available.
"""

from typing import Optional, Dict, Any, List

from ac3.player.player_controller import PlayerController, LoopMode
from ac3.metadata import Player, Song

PROVIDES_CONTROLLERS = ["NullPlayerController"]

class NullPlayerController(PlayerController):
    """
    A PlayerController implementation that does nothing
    
    This controller implements all the required interfaces but has no actual functionality.
    All operations will return False, and all queries will return None or appropriate defaults.
    """
    
    def __init__(self, player_id: str = "null", name: str = "Null Player", **kwargs):
        """
        Initialize the null player controller
        
        Args:
            player_id: Unique identifier for this player (default: "null")
            name: Display name for this player (default: "Null Player")
            **kwargs: Additional configuration parameters (ignored)
        """
        super().__init__(player_id, name, None)
        
    def get_player_info(self) -> Player:
        """
        Get information about the player
        
        Returns:
            A default Player object with minimal information
        """
        return Player(
            name=self.name,
            player_id=self.player_id,
            type="null",
            state="stopped",
            volume=0,
            muted=False,
            capabilities=[],
            active=False,
            supports_seek=False
        )
    
    def get_current_song(self) -> Optional[Song]:
        """
        Get information about the currently playing song
        
        Returns:
            None as no song is playing
        """
        return None
    
    def play(self) -> bool:
        """
        Start or resume playback (no-op)
        
        Returns:
            False as operation is not supported
        """
        # Even though we don't do anything, still notify listeners for consistency
        player_info = self.get_player_info()
        self._notify_player_state_change(player_info)
        return False
    
    def pause(self) -> bool:
        """
        Pause playback (no-op)
        
        Returns:
            False as operation is not supported
        """
        # Even though we don't do anything, still notify listeners for consistency
        player_info = self.get_player_info()
        self._notify_player_state_change(player_info)
        return False
    
    def stop(self) -> bool:
        """
        Stop playback (no-op)
        
        Returns:
            False as operation is not supported
        """
        # Even though we don't do anything, still notify listeners for consistency
        player_info = self.get_player_info()
        self._notify_player_state_change(player_info)
        self._notify_song_change(None)
        return False
    
    def next(self) -> bool:
        """
        Skip to next track (no-op)
        
        Returns:
            False as operation is not supported
        """
        return False
    
    def previous(self) -> bool:
        """
        Skip to previous track (no-op)
        
        Returns:
            False as operation is not supported
        """
        return False
    
    def set_volume(self, volume: int) -> bool:
        """
        Set player volume (no-op)
        
        Args:
            volume: Volume level (0-100)
            
        Returns:
            False as operation is not supported
        """
        return False
    
    def get_volume(self) -> int:
        """
        Get current volume level
        
        Returns:
            0 as default volume level
        """
        return 0
    
    def mute(self, mute: bool = True) -> bool:
        """
        Mute or unmute the player (no-op)
        
        Args:
            mute: True to mute, False to unmute
            
        Returns:
            False as operation is not supported
        """
        return False
    
    def is_muted(self) -> bool:
        """
        Check if player is muted
        
        Returns:
            False as default mute state
        """
        return False
    
    def seek(self, position: float) -> bool:
        """
        Seek to position in current track (no-op)
        
        Args:
            position: Position in seconds
            
        Returns:
            False as operation is not supported
        """
        return False
    
    def get_position(self) -> Optional[float]:
        """
        Get current playback position
        
        Returns:
            None as position is not available
        """
        return None
    
    def set_shuffle(self, enabled: bool) -> bool:
        """
        Enable or disable shuffle mode (no-op)
        
        Args:
            enabled: True to enable shuffle, False to disable
            
        Returns:
            False as operation is not supported
        """
        return False
    
    def get_shuffle(self) -> bool:
        """
        Get current shuffle mode
        
        Returns:
            False as default shuffle state
        """
        return False
    
    def set_loop_mode(self, mode: LoopMode) -> bool:
        """
        Set loop mode (no-op)
        
        Args:
            mode: The loop mode to set (NONE, TRACK, or PLAYLIST)
            
        Returns:
            False as operation is not supported
        """
        return False
    
    def get_loop_mode(self) -> LoopMode:
        """
        Get current loop mode
        
        Returns:
            NONE as default loop mode
        """
        return LoopMode.NONE
    
    def isConnected(self) -> bool:
        """
        Check if the player controller is currently connected
        
        Returns:
            False as this is a null controller
        """
        return False
        
    def isUpdating(self) -> bool:
        """
        Check if the player is currently updating its internal database
        
        Returns:
            False as this is a null controller
        """
        return False
        
    def update(self) -> bool:
        """
        Trigger an update of the player's internal database
        
        Returns:
            False as operation is not supported
        """
        return False