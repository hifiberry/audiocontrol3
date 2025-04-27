"""
MPD Player Controller for AudioControl3

This module provides an implementation of the PlayerController
interface for controlling Music Player Daemon (MPD) servers.
"""

import logging
import threading
import time
from typing import Optional, Dict, Any, List
import mpd  # from python-mpd2 package
from ac3.player.player_controller import PlayerController, LoopMode, PlayerState
from ac3.metadata import Player, Song

logger = logging.getLogger("ac3.player.mpd")

PROVIDES_CONTROLLERS = ["MPDPlayerController"]

# MPD state to PlayerState mapping
MPD_STATE_MAP = {
    "play": PlayerState.PLAYING,
    "pause": PlayerState.PAUSED,
    "stop": PlayerState.STOPPED
}


class MPDPlayerController(PlayerController):
    """
    MPD player implementation using the python-mpd2 library.
    
    This class implements the PlayerController interface to control
    Music Player Daemon (MPD) servers.
    """
    
    def __init__(self, player_id: str = "mpd", configdata: Optional[Dict[str, Any]] = None):
        """
        Initialize the MPD player controller
        
        Args:
            player_id: Unique identifier for this player
            configdata: Configuration data for the player (optional)
        """
        # Default values
        name = "MPD Player"
        host = "localhost"
        port = 6600
        password = None
        timeout = 10.0
        
        # Process configdata if provided
        if configdata is not None:
            player_id = configdata.get("player_id", player_id)
            name = configdata.get("name", name)
            host = configdata.get("host", host)
            port = configdata.get("port", port)
            password = configdata.get("password", password)
            timeout = configdata.get("timeout", timeout)
            
        # Initialize the base class
        super().__init__(player_id, name, configdata)
        
        # Initialize MPD-specific attributes
        self._host = host
        self._port = port
        self._password = password
        self._timeout = timeout
        self._client = None
        self._is_muted = False
        self._volume_before_mute = 100
        
        # Define base capabilities without dynamic ones (will be added conditionally)
        self._base_capabilities = [
            self.CAP_PLAY, self.CAP_PAUSE, self.CAP_PLAYPAUSE,
            self.CAP_STOP, self.CAP_POSITION, 
            self.CAP_LENGTH, self.CAP_VOLUME, self.CAP_MUTE, 
            self.CAP_SHUFFLE, self.CAP_LOOP, self.CAP_PLAYLISTS, 
            self.CAP_QUEUE, self.CAP_METADATA, self.CAP_SEARCH, 
            self.CAP_BROWSE
        ]
        
        # Current capabilities (will be updated as needed)
        self._capabilities = self._base_capabilities.copy()
        
        # Last known playlist position for capability updates
        self._last_song_pos = None
        self._last_playlist_length = None
        
        # Thread control variables
        self._event_listener_thread = None
        self._event_client = None
        self._thread_running = False
        self._last_known_state = {}
        
        # Try to connect to MPD server during initialization
        try:
            self._connect()
            # Start the event listener thread
            self._start_event_listener()
        except Exception as e:
            logger.warning(f"Could not connect to MPD server: {e}")
            
    def __del__(self):
        """Cleanup resources when object is destroyed"""
        self.disconnect()
        
    def _start_event_listener(self):
        """Start background thread to listen for MPD events"""
        if self._event_listener_thread is None or not self._event_listener_thread.is_alive():
            self._thread_running = True
            self._event_listener_thread = threading.Thread(
                target=self._event_listener_loop,
                daemon=True,
                name="MPD-EventListener"
            )
            self._event_listener_thread.start()
            logger.info("MPD event listener thread started")
            
    def _stop_event_listener(self):
        """Stop the event listener thread"""
        if self._event_listener_thread and self._event_listener_thread.is_alive():
            self._thread_running = False
            
            # Unblock the idle call if there is an event client
            if self._event_client:
                try:
                    self._event_client.noidle()
                except Exception:
                    pass

                try:
                    self._event_client.close()
                except Exception:
                    pass

                self._event_client = None
                
            # Wait for the thread to terminate
            self._event_listener_thread.join(2.0)  # Wait up to 2 seconds
                
            logger.info("MPD event listener thread stopped")
    
    def _event_listener_loop(self):
        """
        Background thread that listens for MPD events using idle mode
        
        This method runs in a separate thread and uses MPD's idle mode to receive
        notifications about changes without polling. When changes are received,
        it processes them and notifies any registered listeners.
        """
        # Create a separate MPD client for this thread
        self._event_client = mpd.MPDClient()
        self._event_client.timeout = self._timeout

        while self._thread_running:
            try:
                # Ensure we have a connection
                try:
                    # Try to ping to check if connection is alive
                    self._event_client.ping()
                except Exception:
                    # Need to (re)connect
                    logger.debug("Event listener connecting to MPD")
                    try:
                        # Close any existing connection first
                        try:
                            self._event_client.close()
                        except Exception:
                            pass

                        # Create a new connection
                        self._event_client = mpd.MPDClient()
                        self._event_client.timeout = self._timeout
                        self._event_client.connect(self._host, self._port)
                        if self._password:
                            self._event_client.password(self._password)

                        # Get initial state
                        try:
                            self._last_known_state = {
                                "status": self._event_client.status(),
                                "currentsong": self._event_client.currentsong(),
                            }
                        except Exception as e:
                            logger.error(f"Error getting initial state: {e}")
                            self._last_known_state = {}

                    except Exception as e:
                        logger.warning(f"Failed to connect event client: {e}")
                        time.sleep(2)  # Wait before retrying
                        continue  # Skip to next iteration to retry connection

                # Wait for events (this blocks until something changes or noidle is called)
                logger.debug("Entering MPD idle mode")
                try:
                    changes = self._event_client.idle()

                    # Handle unexpected return value
                    if isinstance(changes, str) and ":" in changes:
                        logger.warning(f"Unexpected return value from MPD idle: {changes}")
                        # Simulate player and mixer changes to force a status update
                        changes = ["player", "mixer"]

                    logger.debug(f"MPD reports changes: {changes}")

                    # Process the reported changes
                    if not self._thread_running:
                        break

                    self._process_mpd_changes(changes)
                except mpd.base.ConnectionError as e:
                    logger.warning(f"MPD connection lost during idle: {e}")
                    time.sleep(1)  # Wait before reconnecting
                    continue  # Skip to next iteration to reconnect
                except Exception as e:
                    logger.error(f"Error during idle: {e}")
                    time.sleep(1)
                    continue

            except Exception as e:
                # Catch-all for any unexpected errors
                logger.error(f"Error in MPD event listener: {e}")
                time.sleep(1)

        # Clean up
        logger.debug("MPD event listener loop exiting")
        try:
            self._event_client.close()
        except Exception:
            pass
        self._event_client = None
    
    def _process_mpd_changes(self, changes):
        """
        Process MPD change notifications and trigger appropriate callbacks

        Args:
            changes: List of subsystems that changed (from MPD idle command)
        """
        try:
            # These are the MPD subsystems we're interested in
            need_status = False
            need_currentsong = False

            # Determine what information we need to fetch based on the changes
            for subsystem in changes:
                if subsystem in ["player", "mixer", "options"]:
                    need_status = True
                if subsystem in ["player"]:
                    need_currentsong = True

            # Fetch the needed information
            current_status = {}
            current_song = {}

            if need_status:
                try:
                    current_status = self._event_client.status()
                except Exception as e:
                    logger.error(f"Error getting status: {e}")

            if need_currentsong:
                try:
                    current_song = self._event_client.currentsong()
                except Exception as e:
                    logger.error(f"Error getting current song: {e}")

            # Process player state changes
            if "player" in changes:
                # Create and send player info
                player = self.get_player_info()
                self._notify_player_state_change(player)

                # Process song change
                old_songid = self._last_known_state.get("status", {}).get("songid")
                new_songid = current_status.get("songid")

                if old_songid != new_songid:
                    song = self.get_current_song()
                    self._notify_song_change(song)

            # Process volume changes
            if "mixer" in changes:
                old_volume = int(self._last_known_state.get("status", {}).get("volume", "0"))
                new_volume = int(current_status.get("volume", "0"))

                if old_volume != new_volume:
                    self._notify_volume_change(new_volume)

            # Process playback position changes
            if "player" in changes:
                if current_status.get("state") == "play":  # MPD uses raw "play" string
                    try:
                        position = float(current_status.get("elapsed", 0))
                        self._notify_position_change(position)
                    except (ValueError, TypeError):
                        pass

            # Update our last known state
            if current_status:
                self._last_known_state["status"] = current_status
            if current_song:
                self._last_known_state["currentsong"] = current_song

            # Update capabilities based on playlist position
            self._update_capabilities(current_status)

        except Exception as e:
            logger.error(f"Error processing MPD changes: {e}")

    def _update_capabilities(self, status):
        """
        Dynamically update capabilities based on playlist position and track properties
        
        Args:
            status: Current MPD status dictionary
        """
        try:
            song_pos = int(status.get("song", -1))
            playlist_length = int(status.get("playlistlength", 0))
            
            # Track if capabilities will change
            old_capabilities = self._capabilities.copy()
            
            # Update capabilities
            self._capabilities = self._base_capabilities.copy()
            
            # Add PREVIOUS capability if we're not at the first song
            if song_pos > 0:
                self._capabilities.append(self.CAP_PREVIOUS)
            else:
                logging.debug("No previous song available, CAP_PREVIOUS not added")
                
            # Add NEXT capability if we're not at the last song
            if song_pos < playlist_length - 1 and playlist_length > 0:
                self._capabilities.append(self.CAP_NEXT)
            else:
                logging.debug("No next song available, CAP_NEXT not added")
            
            # Check if seeking is possible (track has duration and is not a stream)
            is_seekable = False
            
            # Seeking is possible if:
            # 1. A song is playing (state is play or pause)
            # 2. The song has a valid duration
            # 3. The song is not a streaming URL
            if status.get("state") in ["play", "pause"] and song_pos >= 0:
                # Check if track has duration
                if "duration" in status:
                    try:
                        duration = float(status["duration"])
                        # If we have a valid duration, seeking is probably possible
                        # (internet streams typically don't report a duration)
                        if duration > 0:
                            is_seekable = True
                    except (ValueError, TypeError):
                        pass
                
                # If we still think it's seekable, check if it's a stream
                if is_seekable and self._client and self._ensure_connected():
                    try:
                        current = self._client.currentsong()
                        if current and "file" in current:
                            # Check if file appears to be a stream URL
                            file_path = current["file"]
                            if file_path.startswith(("http://", "https://", "mms://", "rtsp://")):
                                # It's a stream, so seeking is likely not possible
                                is_seekable = False
                    except Exception as e:
                        logger.error(f"Error determining if track is seekable: {e}")
            
            # Add seeking capability if appropriate
            if is_seekable:
                self._capabilities.append(self.CAP_SEEK)
            
            # If capabilities changed, notify listeners
            if set(old_capabilities) != set(self._capabilities):
                logger.debug(f"Capabilities changed: {self._capabilities}")
                # Display new and rmeoved capabilities
                added_capabilities = set(self._capabilities) - set(old_capabilities)
                removed_capabilities = set(old_capabilities) - set(self._capabilities)
                if added_capabilities:
                    logger.debug(f"Added capabilities: {added_capabilities}")
                if removed_capabilities:
                    logger.debug(f"Removed capabilities: {removed_capabilities}")
                self._notify_capability_change(self._capabilities)
                
            # Remember current position for future comparisons
            self._last_song_pos = song_pos
            self._last_playlist_length = playlist_length
                
        except Exception as e:
            logger.error(f"Error updating capabilities: {e}")
    
    def _connect(self) -> bool:
        """
        Connect to the MPD server
        
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            if self._client is None:
                self._client = mpd.MPDClient()
                self._client.timeout = self._timeout
            
            # Try to ping the server to check if we're already connected
            try:
                self._client.ping()
                # We're already connected
            except:
                # Need to connect
                self._client.connect(self._host, self._port)
                if self._password:
                    self._client.password(self._password)
                
                # Start the event listener if we've connected successfully
                self._start_event_listener()
            
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MPD server: {e}")
            self._client = None
            return False
    
    def _ensure_connected(self) -> bool:
        """
        Ensure connection to MPD server
        
        Returns:
            True if connected, False otherwise
        """
        try:
            self._client.ping()
            return True
        except Exception as e:
            logger.warning(f"MPD connection lost: {e}")
            return False
    
    def disconnect(self):
        """
        Disconnect from the MPD server and clean up resources
        """
        # Stop the event listener thread first
        self._stop_event_listener()
        
        # Then close the main client connection
        if self._client and self._ensure_connected():
            try:
                self._client.close()
            except Exception as e:
                logger.error(f"Error closing MPD connection: {e}")
            
        self._client = None
    
    def get_player_info(self) -> Player:
        """
        Get information about the player
        
        Returns:
            Player object with current player information
        """
        player = Player(
            name=self.name,
            player_id=self.player_id,
            type="mpd",
            capabilities=self._capabilities,
            active=False
        )
        
        # Try to get current status
        if self._ensure_connected():
            try:
                status = self._client.status()
                
                # Set player state
                mpd_state = status.get("state")
                if mpd_state in MPD_STATE_MAP:
                    player.state = MPD_STATE_MAP[mpd_state]
                else:
                    player.state = PlayerState.UNKNOWN.value
                
                # Set volume
                if "volume" in status:
                    try:
                        player.volume = int(status["volume"])
                    except (ValueError, TypeError):
                        pass
                
                # Set position
                if "elapsed" in status:
                    try:
                        player.position = float(status["elapsed"])
                    except (ValueError, TypeError):
                        pass
                
                # Set muted status
                player.muted = self._is_muted
                
                # Set active state
                player.active = mpd_state == "play"
                
                # Update the capabilities based on playlist position
                self._update_capabilities(status)
                
            except Exception as e:
                logger.error(f"Error getting player info: {e}")
        
        return player
    
    def get_current_song(self) -> Optional[Song]:
        """
        Get information about the currently playing song
        
        Returns:
            Song object with metadata, or None if no song is playing
        """
        if not self._ensure_connected():
            return None
        
        try:
            status = self._client.status()
            # MPD returns string "stop", not the enum
            if status.get("state") == "stop":
                return None
            
            current = self._client.currentsong()
            if not current:
                return None
            
            # Create song object from MPD data
            song = Song(
                title=current.get("title"),
                artist=current.get("artist"),
                album=current.get("album"),
                album_artist=current.get("albumartist"),
                source="mpd"
            )
            
            # Handle track number
            if "track" in current:
                try:
                    # MPD sometimes returns track as "1/10"
                    if "/" in current["track"]:
                        parts = current["track"].split("/")
                        song.track_number = int(parts[0])
                        song.total_tracks = int(parts[1])
                    else:
                        song.track_number = int(current["track"])
                except (ValueError, IndexError):
                    pass
            
            # Handle duration
            if "duration" in current:
                try:
                    song.duration = float(current["duration"])
                except (ValueError, TypeError):
                    pass
            
            # Handle date/year
            if "date" in current:
                try:
                    # Try to extract year from date
                    year_str = current["date"].split("-")[0]
                    song.year = int(year_str)
                except (ValueError, IndexError):
                    pass
            
            # Handle genre
            if "genre" in current:
                song.genre = current["genre"]
                
            return song
        except Exception as e:
            logger.error(f"Error getting current song: {e}")
            return None
    
    def play(self) -> bool:
        """
        Start or resume playback

        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connected():
            return False

        try:
            self._client.play()
            # Notify listeners about the state change
            player_info = self.get_player_info()
            self._notify_player_state_change(player_info)
            song = self.get_current_song()
            self._notify_song_change(song)
            return True
        except mpd.CommandError as e:
            logger.error(f"MPD CommandError while playing: {e}")
            return False
        except Exception as e:
            logger.error(f"Error playing: {e}")
            return False
    
    def pause(self) -> bool:
        """
        Pause playback
        
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connected():
            return False
        
        try:
            self._client.pause(1)
            # Notify listeners about the state change
            player_info = self.get_player_info()
            self._notify_player_state_change(player_info)
            return True
        except Exception as e:
            logger.error(f"Error pausing: {e}")
            return False
    
    def stop(self) -> bool:
        """
        Stop playback
        
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connected():
            return False
        
        try:
            self._client.stop()
            # Notify listeners about the state change
            player_info = self.get_player_info()
            self._notify_player_state_change(player_info)
            self._notify_song_change(None)
            return True
        except Exception as e:
            logger.error(f"Error stopping: {e}")
            return False
    
    def next(self) -> bool:
        """
        Skip to next track
        
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connected():
            return False
        
        try:
            self._client.next()
            # Notify listeners about the song change
            player_info = self.get_player_info()
            self._notify_player_state_change(player_info)
            song = self.get_current_song()
            self._notify_song_change(song)
            return True
        except Exception as e:
            logger.error(f"Error skipping to next track: {e}")
            return False
    
    def previous(self) -> bool:
        """
        Skip to previous track
        
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connected():
            return False
        
        try:
            self._client.previous()
            # Notify listeners about the song change
            player_info = self.get_player_info()
            self._notify_player_state_change(player_info)
            song = self.get_current_song()
            self._notify_song_change(song)
            return True
        except Exception as e:
            logger.error(f"Error skipping to previous track: {e}")
            return False
    
    def set_volume(self, volume: int) -> bool:
        """
        Set player volume
        
        Args:
            volume: Volume level (0-100)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connected():
            return False
        
        try:
            # Ensure volume is within range
            volume = max(0, min(100, volume))
            self._client.setvol(volume)
            
            # If we're setting volume > 0, we're implicitly unmuting
            if volume > 0:
                self._is_muted = False
                
            # Notify listeners about volume change
            self._notify_volume_change(volume)
            
            return True
        except Exception as e:
            logger.error(f"Error setting volume: {e}")
            return False
    
    def get_volume(self) -> int:
        """
        Get current volume level
        
        Returns:
            Current volume level (0-100)
        """
        if not self._ensure_connected():
            return 0
        
        try:
            status = self._client.status()
            if "volume" in status:
                try:
                    return int(status["volume"])
                except (ValueError, TypeError):
                    pass
            return 0
        except Exception as e:
            logger.error(f"Error getting volume: {e}")
            return 0
    
    def mute(self, mute: bool = True) -> bool:
        """
        Mute or unmute the player
        
        Args:
            mute: True to mute, False to unmute
            
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connected():
            return False
        
        try:
            if mute and not self._is_muted:
                # Store current volume and set to 0
                self._volume_before_mute = self.get_volume()
                self._client.setvol(0)
                self._is_muted = True
                
                # Notify listeners about volume change
                self._notify_volume_change(0)
                
                return True
            elif not mute and self._is_muted:
                # Restore previous volume
                self._client.setvol(self._volume_before_mute)
                self._is_muted = False
                
                # Notify listeners about volume change
                self._notify_volume_change(self._volume_before_mute)
                
                return True
            return True  # Already in desired state
        except Exception as e:
            logger.error(f"Error {mute and 'muting' or 'unmuting'}: {e}")
            return False
    
    def is_muted(self) -> bool:
        """
        Check if player is muted
        
        Returns:
            True if muted, False otherwise
        """
        return self._is_muted
    
    def seek(self, position: float) -> bool:
        """
        Seek to position in current track
        
        Args:
            position: Position in seconds
            
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connected():
            return False
        
        try:
            self._client.seekcur(position)
            # Notify listeners about position change
            self._notify_position_change(position)
            return True
        except Exception as e:
            logger.error(f"Error seeking: {e}")
            return False
    
    def get_position(self) -> Optional[float]:
        """
        Get current playback position
        
        Returns:
            Current position in seconds, or None if not available
        """
        if not self._ensure_connected():
            return None
        
        try:
            status = self._client.status()
            if "elapsed" in status:
                try:
                    return float(status["elapsed"])
                except (ValueError, TypeError):
                    pass
            return None
        except Exception as e:
            logger.error(f"Error getting position: {e}")
            return None
    
    def set_shuffle(self, enabled: bool) -> bool:
        """
        Enable or disable shuffle mode
        
        Args:
            enabled: True to enable shuffle, False to disable
            
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connected():
            return False
        
        try:
            self._client.random(1 if enabled else 0)
            return True
        except Exception as e:
            logger.error(f"Error setting shuffle: {e}")
            return False
    
    def get_shuffle(self) -> bool:
        """
        Get current shuffle mode
        
        Returns:
            True if shuffle is enabled, False otherwise
        """
        if not self._ensure_connected():
            return False
        
        try:
            status = self._client.status()
            return status.get("random", "0") == "1"
        except Exception as e:
            logger.error(f"Error getting shuffle status: {e}")
            return False
    
    def set_loop_mode(self, mode: LoopMode) -> bool:
        """
        Set loop mode
        
        Args:
            mode: The loop mode to set (NONE, TRACK, or PLAYLIST)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connected():
            return False
        
        try:
            if mode == LoopMode.NONE:
                # No repeat, no single
                self._client.repeat(0)
                self._client.single(0)
            elif mode == LoopMode.TRACK:
                # Enable single mode
                self._client.repeat(1)
                self._client.single(1)
            elif mode == LoopMode.PLAYLIST:
                # Enable repeat, disable single
                self._client.repeat(1)
                self._client.single(0)
            return True
        except Exception as e:
            logger.error(f"Error setting loop mode: {e}")
            return False
    
    def get_loop_mode(self) -> LoopMode:
        """
        Get current loop mode
        
        Returns:
            Current loop mode (NONE, TRACK, or PLAYLIST)
        """
        if not self._ensure_connected():
            return LoopMode.NONE
        
        try:
            status = self._client.status()
            repeat = status.get("repeat", "0") == "1"
            single = status.get("single", "0") == "1"
            
            if not repeat:
                return LoopMode.NONE
            elif single:
                return LoopMode.TRACK
            else:
                return LoopMode.PLAYLIST
        except Exception as e:
            logger.error(f"Error getting loop mode: {e}")
            return LoopMode.NONE
    
    def isConnected(self) -> bool:
        """
        Check if the player controller is currently connected to its underlying player service
        
        Returns:
            True if connected, False otherwise
        """
        return self._ensure_connected()
    
    def isUpdating(self) -> bool:
        """
        Check if the MPD server is currently updating its internal database
        
        Returns:
            True if updating, False otherwise
        """
        if not self._ensure_connected():
            return False
        
        try:
            status = self._client.status()
            # MPD indicates database update with an "updating_db" key in the status
            return "updating_db" in status
        except Exception as e:
            logger.error(f"Error checking database update status: {e}")
            return False
            
    def update(self) -> bool:
        """
        Trigger a database update in the MPD server
        
        This instructs MPD to rescan its music directory for new or changed files
        and update its internal database accordingly.
        
        Returns:
            True if the update was successfully triggered, False otherwise
        """
        if not self._ensure_connected():
            return False
            
        try:
            # The update command returns the update job ID if successful
            update_id = self._client.update()
            logger.info(f"MPD database update triggered, job ID: {update_id}")
            return True
        except Exception as e:
            logger.error(f"Error triggering MPD database update: {e}")
            return False
    
    def isActive(self) -> bool:
        """
        Check if the player is currently active (playing)
        
        Returns:
            True if the player is currently playing, False otherwise
        """
        if not self._ensure_connected():
            return False
        
        try:
            status = self._client.status()
            # Compare with raw MPD state string, not enum
            return status.get("state") == "play"
        except Exception as e:
            logger.error(f"Error checking if player is active: {e}")
            return False