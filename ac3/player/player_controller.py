"""
Player Controller Abstract Base Class

This module defines the abstract interface that all player controllers must implement.
"""

import importlib
import logging
import os
import pkgutil
import sys
import inspect
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Type, Callable, Set
from enum import Enum, auto
from ac3.metadata import Player, Song

logger = logging.getLogger("ac3.player")


class LoopMode(Enum):
    """Loop mode for playback"""
    NONE = "no"       # No loop
    TRACK = "song"    # Loop current track/song
    PLAYLIST = "playlist"  # Loop entire playlist


class PlayerState(Enum):
    """Player state enum defining possible states a player can be in"""
    PLAYING = "playing"   # Player is actively playing media
    PAUSED = "paused"     # Playback is paused
    STOPPED = "stopped"   # Playback is stopped
    KILLED = "killed"     # Player process has been killed or crashed
    UNKNOWN = "unknown"   # Player state cannot be determined

    def __str__(self):
        """Return the value as a string for backwards compatibility"""
        return self.value


class PlayerStateListener(ABC):
    """
    Interface for receiving player state updates
    
    Classes that want to receive updates from a PlayerController should
    implement this interface and register themselves with the controller.
    """
    
    def on_player_state_change(self, player: Player) -> None:
        """
        Called when the player state changes
        
        Args:
            player: Updated player information
        """
        pass
    
    def on_song_change(self, song: Optional[Song]) -> None:
        """
        Called when the current song changes
        
        Args:
            song: New song information, or None if no song is playing
        """
        pass
    
    def on_volume_change(self, volume: int) -> None:
        """
        Called when the player volume changes
        
        Args:
            volume: New volume level (0-100)
        """
        pass
    
    def on_position_change(self, position: Optional[float]) -> None:
        """
        Called when the playback position changes
        
        Args:
            position: New position in seconds, or None if not available
        """
        pass
    
    def on_capability_change(self, capabilities: List[str]) -> None:
        """
        Called when the player's capabilities change
        
        Args:
            capabilities: List of currently available capability strings
        """
        pass


class PlayerController(ABC):
    """
    Abstract base class for player controllers.
    
    A PlayerController provides an interface for controlling and retrieving
    information from a specific media player (e.g., MPD, Spotify, Bluetooth).
    
    All player implementation classes should inherit from this class
    and implement the required abstract methods.
    """
    # Capability constants
    CAP_PLAY = "play"                 # Can play media
    CAP_PAUSE = "pause"               # Can pause playback
    CAP_PLAYPAUSE = "playpause"       # Can toggle between play and pause
    CAP_STOP = "stop"                 # Can stop playback
    CAP_NEXT = "next"                 # Can skip to next track
    CAP_PREVIOUS = "previous"         # Can skip to previous track
    CAP_SEEK = "seek"                 # Can seek within a track
    CAP_POSITION = "position"         # Can report playback position
    CAP_LENGTH = "length"             # Can report track duration/length
    CAP_VOLUME = "volume"             # Can control volume
    CAP_MUTE = "mute"                 # Can mute/unmute
    CAP_SHUFFLE = "shuffle"           # Can toggle shuffle mode
    CAP_LOOP = "loop"                 # Can set loop mode
    CAP_PLAYLISTS = "playlists"       # Can manage playlists
    CAP_QUEUE = "queue"               # Can manage queue
    CAP_METADATA = "metadata"         # Can provide metadata
    CAP_ALBUM_ART = "album_art"       # Can provide album art
    CAP_SEARCH = "search"             # Can search for tracks
    CAP_BROWSE = "browse"             # Can browse media library
    CAP_FAVORITES = "favorites"       # Can manage favorites
    CAP_DATABASE_UPDATE = "db_update" # Can update internal database
    
    # Event types for callbacks
    EVENT_PLAYER_STATE_CHANGE = "player_state_change"
    EVENT_SONG_CHANGE = "song_change"
    EVENT_VOLUME_CHANGE = "volume_change"
    EVENT_POSITION_CHANGE = "position_change"
    EVENT_CAPABILITY_CHANGE = "capability_change"
    EVENT_CONNECTION_CHANGE = "connection_change"
    EVENT_UPDATE_STATUS_CHANGE = "update_status_change"
    EVENT_PLAYLIST_CHANGE = "playlist_change"
    EVENT_QUEUE_CHANGE = "queue_change"
    
    @classmethod
    def controllerImplementations(cls) -> List[str]:
        """
        List all available player controller implementations
        
        This method scans the ac3.player package to find all modules that
        contain controller implementations that can be used with createController().
        
        Returns:
            List of player type names that can be used with createController()
        """
        implementations = []
        
        try:
            # Get the directory of the current module
            import ac3.player
            pkg_dir = os.path.dirname(ac3.player.__file__)
            
            # Find all Python modules in this directory
            for _, module_name, is_pkg in pkgutil.iter_modules([pkg_dir]):
                # Skip __init__, this controller module, and packages
                if module_name == "__init__" or module_name == "player_controller" or is_pkg:
                    continue
                
                try:
                    # Try to import the module
                    module = importlib.import_module(f"ac3.player.{module_name}")
                    
                    # Look for controller classes in the module
                    for name, obj in inspect.getmembers(module):
                        if (inspect.isclass(obj) and 
                            issubclass(obj, PlayerController) and 
                            obj != PlayerController and
                            name.endswith("PlayerController")):
                            
                            # Extract player type from class name (e.g., MPDPlayerController -> mpd)
                            player_type = name[:-16].lower()
                            implementations.append(player_type)
                
                except ImportError as e:
                    logger.warning(f"Could not import module ac3.player.{module_name}: {e}")
                except Exception as e:
                    logger.warning(f"Error processing module ac3.player.{module_name}: {e}")
        
        except Exception as e:
            logger.error(f"Error listing controller implementations: {e}")
        
        # Log the discovered implementations for debugging
        logger.info(f"Discovered player controller implementations: {implementations}")
        
        return sorted(implementations)
    
    def __init__(self, player_id: str, name: str, configdata: Optional[Dict[str, Any]] = None):
        """
        Initialize the player controller
        
        Args:
            player_id: Unique identifier for this player
            name: Display name for this player
            configdata: Configuration data for the player (optional)
        """
        self._player_id = player_id
        self._name = name
        self._state_listeners: Set[PlayerStateListener] = set()
        # Dictionary to store callbacks by event type
        self._callbacks: Dict[str, List[Callable[..., None]]] = {}
    
    def register_callback(self, event_type: str, callback: Callable[..., None]) -> None:
        """
        Register a callback function for a specific event type
        
        Args:
            event_type: The event type to register for
            callback: The callback function to call when the event occurs
                      The callback function will receive event-specific arguments
        """
        if event_type not in self._callbacks:
            self._callbacks[event_type] = []
        if callback not in self._callbacks[event_type]:
            self._callbacks[event_type].append(callback)
            logger.debug(f"Registered callback for event {event_type}: {callback}")
    
    def unregister_callback(self, event_type: str, callback: Callable[..., None]) -> None:
        """
        Unregister a previously registered callback function
        
        Args:
            event_type: The event type to unregister from
            callback: The callback function to unregister
        """
        if event_type in self._callbacks and callback in self._callbacks[event_type]:
            self._callbacks[event_type].remove(callback)
            logger.debug(f"Unregistered callback for event {event_type}: {callback}")
            if not self._callbacks[event_type]:
                del self._callbacks[event_type]
    
    def trigger_callback(self, event_type: str, *args: Any, **kwargs: Any) -> None:
        """
        Trigger callbacks for a specific event type
        
        Args:
            event_type: The event type to trigger callbacks for
            *args: Positional arguments to pass to the callbacks
            **kwargs: Keyword arguments to pass to the callbacks
        """
        if event_type in self._callbacks:
            for callback in list(self._callbacks[event_type]):
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error in callback for event {event_type}: {e}")
    
    def add_state_listener(self, listener: PlayerStateListener) -> None:
        """
        Add a listener to receive player state updates
        
        Args:
            listener: The listener to add
        """
        self._state_listeners.add(listener)
        
    def remove_state_listener(self, listener: PlayerStateListener) -> None:
        """
        Remove a previously added listener
        
        Args:
            listener: The listener to remove
        """
        self._state_listeners.discard(listener)
        
    def _notify_player_state_change(self, player: Player) -> None:
        """
        Notify all listeners about a player state change
        
        Args:
            player: Updated player information
        """
        for listener in list(self._state_listeners):
            try:
                listener.on_player_state_change(player)
            except Exception as e:
                logger.error(f"Error notifying listener {listener}: {e}")
        
        # Also trigger callbacks
        self.trigger_callback(self.EVENT_PLAYER_STATE_CHANGE, player)
                
    def _notify_song_change(self, song: Optional[Song]) -> None:
        """
        Notify all listeners about a song change
        
        Args:
            song: New song information
        """
        for listener in list(self._state_listeners):
            try:
                listener.on_song_change(song)
            except Exception as e:
                logger.error(f"Error notifying listener {listener}: {e}")
        
        # Also trigger callbacks
        self.trigger_callback(self.EVENT_SONG_CHANGE, song)
                
    def _notify_volume_change(self, volume: int) -> None:
        """
        Notify all listeners about a volume change
        
        Args:
            volume: New volume level
        """
        for listener in list(self._state_listeners):
            try:
                listener.on_volume_change(volume)
            except Exception as e:
                logger.error(f"Error notifying listener {listener}: {e}")
        
        # Also trigger callbacks
        self.trigger_callback(self.EVENT_VOLUME_CHANGE, volume)
                
    def _notify_position_change(self, position: Optional[float]) -> None:
        """
        Notify all listeners about a position change
        
        Args:
            position: New playback position
        """
        for listener in list(self._state_listeners):
            try:
                listener.on_position_change(position)
            except Exception as e:
                logger.error(f"Error notifying listener {listener}: {e}")
        
        # Also trigger callbacks
        self.trigger_callback(self.EVENT_POSITION_CHANGE, position)
                
    def _notify_capability_change(self, capabilities: List[str]) -> None:
        """
        Notify all listeners about a capability change
        
        Args:
            capabilities: List of currently available capabilities
        """
        for listener in list(self._state_listeners):
            try:
                listener.on_capability_change(capabilities)
            except Exception as e:
                logger.error(f"Error notifying listener {listener} about capability change: {e}")
        
        # Also trigger callbacks
        self.trigger_callback(self.EVENT_CAPABILITY_CHANGE, capabilities)

    def _notify_connection_change(self, connected: bool) -> None:
        """
        Notify about connection state change
        
        Args:
            connected: Whether the player is connected
        """
        # Trigger callbacks only (no corresponding listener method)
        self.trigger_callback(self.EVENT_CONNECTION_CHANGE, connected)
    
    def _notify_update_status_change(self, updating: bool) -> None:
        """
        Notify about database update status change
        
        Args:
            updating: Whether the database is being updated
        """
        # Trigger callbacks only (no corresponding listener method)
        self.trigger_callback(self.EVENT_UPDATE_STATUS_CHANGE, updating)
    
    def _notify_playlist_change(self) -> None:
        """
        Notify that playlists have changed
        """
        # Trigger callbacks only (no corresponding listener method)
        self.trigger_callback(self.EVENT_PLAYLIST_CHANGE)
    
    def _notify_queue_change(self) -> None:
        """
        Notify that the playback queue has changed
        """
        # Trigger callbacks only (no corresponding listener method)
        self.trigger_callback(self.EVENT_QUEUE_CHANGE)
    
    @classmethod
    def createController(cls, name: str, configdata: Optional[Dict[str, Any]] = None) -> Optional['PlayerController']:
        """
        Create a player controller instance based on the player name
        
        Args:
            name: Name of the player type (e.g., 'mpd', 'spotify')
            configdata: Configuration data for the player (optional)
            
        Returns:
            PlayerController instance if successful, None otherwise
        """
        try:
            # Try to import the module for this player type
            module_name = f"ac3.player.{name.lower()}"
            # Log the module and class names being resolved for debugging
            logger.debug(f"Attempting to import module: {module_name}")
            module = importlib.import_module(module_name)
            if hasattr(module, "PROVIDES_CONTROLLERS"):
                for controller_class_name in module.PROVIDES_CONTROLLERS:
                    if controller_class_name.lower() == f"{name.lower()}playercontroller":
                        controller_class = getattr(module, controller_class_name)
                        break
                else:
                    raise AttributeError(f"Controller class for {name} not found in PROVIDES_CONTROLLERS")
            else:
                raise AttributeError(f"Module {module_name} does not define PROVIDES_CONTROLLERS")
            
            # Create an instance of the controller
            logger.info(f"Creating player controller for {name}")
            
            # If configdata is None, use an empty dict
            if configdata is None:
                configdata = {}
                
            return controller_class(**configdata)
            
        except ImportError:
            logger.error(f"Could not find player module for {name}")
        except AttributeError as e:
            logger.error(f"Error locating controller class for {name}: {e}")
        except Exception as e:
            logger.error(f"Error creating controller for {name}: {e}")
            
        return None
    
    @property
    def player_id(self) -> str:
        """Return the player identifier"""
        return self._player_id
    
    @property
    def name(self) -> str:
        """Return the player name"""
        return self._name
    
    def get_player_info(self) -> Player:
        """
        Get information about the player
        
        Returns:
            Player object with current player information
        """
        return Player(
            name=self.name,
            player_id=self.player_id,
            type="generic",
            capabilities=[],
            active=False,
            state=PlayerState.STOPPED.value,
            volume=0,
            muted=False
        )

    def get_current_song(self) -> Optional[Song]:
        """
        Get information about the currently playing song
        
        Returns:
            None by default, as no song is playing
        """
        return None

    def play(self) -> bool:
        """
        Start or resume playback
        
        Returns:
            False by default, as operation is not supported
        """
        return False

    def pause(self) -> bool:
        """
        Pause playback
        
        Returns:
            False by default, as operation is not supported
        """
        return False

    def stop(self) -> bool:
        """
        Stop playback
        
        Returns:
            False by default, as operation is not supported
        """
        return False

    def next(self) -> bool:
        """
        Skip to next track
        
        Returns:
            False by default, as operation is not supported
        """
        return False

    def previous(self) -> bool:
        """
        Skip to previous track
        
        Returns:
            False by default, as operation is not supported
        """
        return False

    def set_volume(self, volume: int) -> bool:
        """
        Set player volume
        
        Args:
            volume: Volume level (0-100)
        
        Returns:
            False by default, as operation is not supported
        """
        return False

    def get_volume(self) -> int:
        """
        Get current volume level
        
        Returns:
            0 by default, as no volume is set
        """
        return 0

    def mute(self, mute: bool = True) -> bool:
        """
        Mute or unmute the player
        
        Args:
            mute: True to mute, False to unmute
        
        Returns:
            False by default, as operation is not supported
        """
        return False

    def is_muted(self) -> bool:
        """
        Check if player is muted
        
        Returns:
            False by default, as player is not muted
        """
        return False

    def seek(self, position: float) -> bool:
        """
        Seek to position in current track
        
        Args:
            position: Position in seconds
        
        Returns:
            False by default, as operation is not supported
        """
        return False

    def get_position(self) -> Optional[float]:
        """
        Get current playback position
        
        Returns:
            None by default, as no position is available
        """
        return None

    def set_shuffle(self, enabled: bool) -> bool:
        """
        Enable or disable shuffle mode
        
        Args:
            enabled: True to enable shuffle, False to disable
        
        Returns:
            False by default, as operation is not supported
        """
        return False

    def get_shuffle(self) -> bool:
        """
        Get current shuffle mode
        
        Returns:
            False by default, as shuffle is not enabled
        """
        return False

    def set_loop_mode(self, mode: LoopMode) -> bool:
        """
        Set loop mode
        
        Args:
            mode: The loop mode to set (NONE, TRACK, or PLAYLIST)
        
        Returns:
            False by default, as operation is not supported
        """
        return False

    def get_loop_mode(self) -> LoopMode:
        """
        Get current loop mode
        
        Returns:
            LoopMode.NONE by default, as no loop mode is set
        """
        return LoopMode.NONE

    def isConnected(self) -> bool:
        """
        Check if the player controller is currently connected
        
        Returns:
            False by default, as no connection is established
        """
        return False

    def isUpdating(self) -> bool:
        """
        Check if the player is currently updating its internal database
        
        Returns:
            False by default, as no update is in progress
        """
        return False

    def update(self) -> bool:
        """
        Trigger an update of the player's internal database
        
        Returns:
            False by default, as operation is not supported
        """
        return False

    def isActive(self) -> bool:
        """
        Check if the player is currently active (playing)
        
        Returns:
            True if the player state is 'playing', False otherwise
        """
        player_info = self.get_player_info()
        return player_info.state == PlayerState.PLAYING.value if player_info and player_info.state else False
    
    def supports(self, feature: str) -> bool:
        """
        Check if player supports a specific feature
        
        Args:
            feature: Feature name to check
            
        Returns:
            True if feature is supported, False otherwise
        """
        capabilities = self.get_player_info().capabilities
        return capabilities is not None and feature in capabilities