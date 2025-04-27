"""
Audio Controller for AudioControl3

This module provides the main AudioController class that manages multiple
player controllers (e.g., MPD, Spotify, Bluetooth) and provides a unified
interface for controlling them.
"""

import logging
import threading
from typing import Dict, List, Optional, Any, Set, Callable

from ac3.player.player_controller import PlayerController, LoopMode
from ac3.metadata import Player, Song

logger = logging.getLogger("ac3.controller")

class AudioController:
    """
    Main audio controller that manages multiple player controllers
    
    The AudioController provides a unified interface for interacting with multiple
    audio player backends such as MPD, Spotify, etc. It keeps track of the currently
    active player and forwards control commands to it.
    """
    
    def __init__(self):
        """Initialize the audio controller"""
        self._controllers: Dict[str, PlayerController] = {}
        self._active_controller_id: Optional[str] = None
        self._lock = threading.RLock()
        self._listeners: Set[Callable] = set()
        self._auto_pause = True  # Default: pause other players when a new one becomes active
        
    @property
    def auto_pause(self) -> bool:
        """
        Get the current auto-pause setting
        
        Returns:
            True if other players should be paused when a new one becomes active
        """
        return self._auto_pause
    
    @auto_pause.setter
    def auto_pause(self, value: bool) -> None:
        """
        Set the auto-pause behavior
        
        Args:
            value: True to automatically pause other players when a new one becomes active
        """
        self._auto_pause = value
    
    def pause_other_controllers(self) -> None:
        """
        Pause all controllers except the active one
        """
        if not self._active_controller_id:
            return
            
        for player_id, controller in self._controllers.items():
            if player_id != self._active_controller_id:
                try:
                    player_info = controller.get_player_info()
                    if player_info and player_info.state == "playing":
                        logger.info(f"Auto-pausing player: {player_id}")
                        controller.pause()
                except Exception as e:
                    logger.error(f"Error pausing controller {player_id}: {e}")
    
    def register_controller(self, controller: PlayerController) -> bool:
        """
        Register a player controller with the audio controller
        
        Args:
            controller: The PlayerController instance to register
            
        Returns:
            True if registration was successful, False otherwise
        """
        with self._lock:
            player_id = controller.player_id
            
            # Check if this controller ID is already registered
            if player_id in self._controllers:
                logger.warning(f"Controller {player_id} already registered")
                return False
                
            # Register the controller
            self._controllers[player_id] = controller
            logger.info(f"Registered controller {player_id} ({controller.name})")
            
            # If this is the first controller, make it active
            if self._active_controller_id is None:
                self._active_controller_id = player_id
                logger.info(f"Set {player_id} as active controller")
                
            return True
    
    def unregister_controller(self, player_id: str) -> bool:
        """
        Unregister a player controller
        
        Args:
            player_id: ID of the controller to unregister
            
        Returns:
            True if unregistration was successful, False otherwise
        """
        with self._lock:
            if player_id not in self._controllers:
                logger.warning(f"Controller {player_id} not registered")
                return False
                
            # Remove the controller
            controller = self._controllers.pop(player_id)
            logger.info(f"Unregistered controller {player_id} ({controller.name})")
            
            # If this was the active controller, select a new one
            if self._active_controller_id == player_id:
                if self._controllers:
                    # Pick the first available controller
                    self._active_controller_id = next(iter(self._controllers))
                    logger.info(f"Set {self._active_controller_id} as active controller")
                else:
                    # No controllers left
                    self._active_controller_id = None
                    logger.info("No controllers registered")
                    
            return True
    
    def get_controller(self, player_id: str) -> Optional[PlayerController]:
        """
        Get a specific controller by ID
        
        Args:
            player_id: ID of the controller to get
            
        Returns:
            The PlayerController instance, or None if not found
        """
        return self._controllers.get(player_id)
    
    def get_controllers(self) -> List[PlayerController]:
        """
        Get all registered controllers
        
        Returns:
            List of all registered PlayerController instances
        """
        return list(self._controllers.values())
    
    def get_controller_ids(self) -> List[str]:
        """
        Get IDs of all registered controllers
        
        Returns:
            List of controller IDs
        """
        return list(self._controllers.keys())
    
    @property
    def active_controller(self) -> Optional[PlayerController]:
        """
        Get the currently active controller
        
        Returns:
            The active PlayerController instance, or None if none is active
        """
        if self._active_controller_id is None:
            return None
        return self._controllers.get(self._active_controller_id)
    
    @property
    def active_controller_id(self) -> Optional[str]:
        """
        Get the ID of the currently active controller
        
        Returns:
            The ID of the active controller, or None if none is active
        """
        return self._active_controller_id
    
    def set_active_controller(self, player_id: str) -> bool:
        """
        Set the active controller
        
        Args:
            player_id: ID of the controller to make active
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            if player_id not in self._controllers:
                logger.warning(f"Cannot set active controller: {player_id} not registered")
                return False
                
            # Check if it's already active
            if self._active_controller_id == player_id:
                return True
                
            # Set new active controller
            self._active_controller_id = player_id
            logger.info(f"Set {player_id} as active controller")
            
            # If auto_pause is enabled, pause other players
            if self._auto_pause:
                self.pause_other_controllers()
            
            return True
    
    def auto_select_active_controller(self) -> bool:
        """
        Automatically select an active controller based on player state
        
        Selects the first controller that's currently playing, or if none is playing,
        the first controller that's connected.
        
        Returns:
            True if a controller was selected, False otherwise
        """
        with self._lock:
            # First look for a controller that's playing
            for player_id, controller in self._controllers.items():
                if controller.isActive():
                    # If we're changing the active controller and auto_pause is enabled,
                    # we'll need to pause other players
                    old_active_id = self._active_controller_id
                    self._active_controller_id = player_id
                    logger.info(f"Auto-selected {player_id} as active controller (playing)")
                    
                    # If we switched active controllers and auto_pause is enabled, pause others
                    if self._auto_pause and old_active_id != player_id:
                        self.pause_other_controllers()
                    
                    return True
            
            # Then look for a controller that's connected
            for player_id, controller in self._controllers.items():
                if controller.isConnected():
                    self._active_controller_id = player_id
                    logger.info(f"Auto-selected {player_id} as active controller (connected)")
                    return True
            
            logger.warning("No suitable controller found for auto-selection")
            return False
    
    def get_active_player_info(self) -> Optional[Player]:
        """
        Get information about the active player
        
        Returns:
            Player object with current player information, or None if no active player
        """
        controller = self.active_controller
        return controller.get_player_info() if controller else None
    
    def get_all_player_info(self) -> Dict[str, Player]:
        """
        Get information about all registered players
        
        Returns:
            Dictionary mapping player IDs to Player objects
        """
        result = {}
        for player_id, controller in self._controllers.items():
            try:
                result[player_id] = controller.get_player_info()
            except Exception as e:
                logger.error(f"Error getting player info for {player_id}: {e}")
        return result
    
    def get_current_song(self) -> Optional[Song]:
        """
        Get information about the currently playing song on the active player
        
        Returns:
            Song object with metadata, or None if no song is playing
        """
        controller = self.active_controller
        return controller.get_current_song() if controller else None
    
    # Playback control methods - forward to active controller
    
    def play(self) -> bool:
        """
        Start or resume playback on the active player
        
        Returns:
            True if successful, False otherwise
        """
        controller = self.active_controller
        if controller:
            return controller.play()
        logger.warning("Cannot play: no active controller")
        return False
    
    def pause(self) -> bool:
        """
        Pause playback on the active player
        
        Returns:
            True if successful, False otherwise
        """
        controller = self.active_controller
        if controller:
            return controller.pause()
        logger.warning("Cannot pause: no active controller")
        return False
    
    def stop(self) -> bool:
        """
        Stop playback on the active player
        
        Returns:
            True if successful, False otherwise
        """
        controller = self.active_controller
        if controller:
            return controller.stop()
        logger.warning("Cannot stop: no active controller")
        return False
    
    def next(self) -> bool:
        """
        Skip to next track on the active player
        
        Returns:
            True if successful, False otherwise
        """
        controller = self.active_controller
        if controller:
            return controller.next()
        logger.warning("Cannot skip to next: no active controller")
        return False
    
    def previous(self) -> bool:
        """
        Skip to previous track on the active player
        
        Returns:
            True if successful, False otherwise
        """
        controller = self.active_controller
        if controller:
            return controller.previous()
        logger.warning("Cannot skip to previous: no active controller")
        return False
    
    def set_volume(self, volume: int) -> bool:
        """
        Set volume on the active player
        
        Args:
            volume: Volume level (0-100)
            
        Returns:
            True if successful, False otherwise
        """
        controller = self.active_controller
        if controller:
            return controller.set_volume(volume)
        logger.warning("Cannot set volume: no active controller")
        return False
    
    def get_volume(self) -> Optional[int]:
        """
        Get current volume level of the active player
        
        Returns:
            Current volume level (0-100), or None if no active player
        """
        controller = self.active_controller
        return controller.get_volume() if controller else None
    
    def mute(self, mute: bool = True) -> bool:
        """
        Mute or unmute the active player
        
        Args:
            mute: True to mute, False to unmute
            
        Returns:
            True if successful, False otherwise
        """
        controller = self.active_controller
        if controller:
            return controller.mute(mute)
        logger.warning("Cannot mute: no active controller")
        return False
    
    def is_muted(self) -> Optional[bool]:
        """
        Check if active player is muted
        
        Returns:
            True if muted, False if not muted, None if no active player
        """
        controller = self.active_controller
        return controller.is_muted() if controller else None
    
    def seek(self, position: float) -> bool:
        """
        Seek to position in current track on active player
        
        Args:
            position: Position in seconds
            
        Returns:
            True if successful, False otherwise
        """
        controller = self.active_controller
        if controller:
            return controller.seek(position)
        logger.warning("Cannot seek: no active controller")
        return False
    
    def get_position(self) -> Optional[float]:
        """
        Get current playback position of active player
        
        Returns:
            Current position in seconds, or None if not available
        """
        controller = self.active_controller
        return controller.get_position() if controller else None
    
    def set_shuffle(self, enabled: bool) -> bool:
        """
        Enable or disable shuffle mode on active player
        
        Args:
            enabled: True to enable shuffle, False to disable
            
        Returns:
            True if successful, False otherwise
        """
        controller = self.active_controller
        if controller:
            return controller.set_shuffle(enabled)
        logger.warning("Cannot set shuffle mode: no active controller")
        return False
    
    def get_shuffle(self) -> Optional[bool]:
        """
        Get current shuffle mode of active player
        
        Returns:
            True if shuffle is enabled, False if disabled, None if no active player
        """
        controller = self.active_controller
        return controller.get_shuffle() if controller else None
    
    def set_loop_mode(self, mode: LoopMode) -> bool:
        """
        Set loop mode on active player
        
        Args:
            mode: The loop mode to set (NONE, TRACK, or PLAYLIST)
            
        Returns:
            True if successful, False otherwise
        """
        controller = self.active_controller
        if controller:
            return controller.set_loop_mode(mode)
        logger.warning("Cannot set loop mode: no active controller")
        return False
    
    def get_loop_mode(self) -> Optional[LoopMode]:
        """
        Get current loop mode of active player
        
        Returns:
            Current loop mode, or None if no active player
        """
        controller = self.active_controller
        return controller.get_loop_mode() if controller else None
