"""
Text-based UI for AudioControl3

This module provides a curses-based terminal interface for controlling
the AudioController. It displays player state, current track, and provides
keyboard shortcuts for common actions.
"""

import curses
import threading
import time
import logging
from typing import Optional, Dict, Any, Callable, List

from ac3.audio_controller import AudioController, EventType
from ac3.metadata import Player, Song
from ac3.player.player_controller import PlayerController, PlayerState

logger = logging.getLogger("ac3.ui.textui")

class UIUpdater(threading.Thread):
    """
    Background thread to update the play position in the TextUI when no messages
    are received from the AudioController. This ensures the position progresses
    automatically as long as the state is playing and the position is before
    the end of the song.
    """
    def __init__(self, text_ui: 'TextUI'):
        super().__init__(daemon=True)
        self.text_ui = text_ui
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            try:
                if (self.text_ui.current_player and 
                    self.text_ui.current_player.state == PlayerState.PLAYING and
                    self.text_ui.current_song and
                    self.text_ui.current_position is not None and
                    self.text_ui.current_position < self.text_ui.current_song.duration):
                    
                    # Increment the position by 1 second
                    self.text_ui.current_position += 1
                    self.text_ui._request_screen_update()

                time.sleep(1)  # Update once per second
            except Exception as e:
                logger.error(f"Error in UIUpdater: {e}")

    def stop(self):
        self.running = False

class TextUI:
    """
    Text-based UI for AudioControl3 using curses
    
    Provides a simple ncurses interface to control an AudioController
    and display current player state, metadata, and volume.
    """
    
    # Key bindings
    KEY_QUIT = ord('q')
    KEY_PLAY = ord(' ')  # Spacebar now handles both play/pause
    KEY_PAUSE = ord(' ')  # Spacebar
    KEY_STOP = ord('s')
    KEY_NEXT = ord('n')
    KEY_PREV = ord('p')  # Changed from 'b' to 'p'
    KEY_VOLUME_UP = ord('+')
    KEY_VOLUME_DOWN = ord('-')
    KEY_MUTE = ord('m')
    KEY_SHUFFLE = ord('r')
    KEY_LOOP = ord('l')
    KEY_SEEK_FWD = curses.KEY_RIGHT
    KEY_SEEK_BACK = curses.KEY_LEFT
    KEY_REFRESH = ord('R')
    KEY_SWITCH_CONTROLLER = ord('c')
    
    def __init__(self, audio_controller: AudioController):
        """
        Initialize the Text UI
        
        Args:
            audio_controller: The AudioController instance to control
        """
        self.audio_controller = audio_controller
        self.stdscr = None
        self.running = False
        self.update_thread = None
        self.current_player: Optional[Player] = None
        self.current_song: Optional[Song] = None
        self.current_volume: int = 0
        self.current_position: Optional[float] = None
        self.message: str = ""
        self.message_timeout: float = 0
        self.registered_callbacks: List[tuple] = []
        
        # Add a timestamp to track when updates are requested
        self.last_update_request = 0
        # Add a lock to protect access to the timestamp
        self.update_lock = threading.Lock()
        # Set an update interval to avoid too frequent updates
        self.min_update_interval = 0.1  # seconds

        self.ui_updater = UIUpdater(self)
        self.can_next = False
        self.can_previous = False
    
    def start(self):
        """
        Start the text UI
        """
        # Register callbacks for player events
        self._register_player_callbacks()
        
        # Initialize curses
        self.stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        curses.curs_set(0)  # Hide cursor
        self.stdscr.keypad(True)
        self.stdscr.timeout(100)  # Non-blocking input with 100ms timeout
        
        # Start in a try-finally block to ensure proper cleanup
        try:
            # Start update thread (less frequent updates as a backup)
            self.running = True
            self.update_thread = threading.Thread(target=self._update_info_thread)
            self.update_thread.daemon = True
            self.update_thread.start()

            # Start UIUpdater thread
            self.ui_updater.start()
            
            # Run main loop
            self._main_loop()
            
        finally:
            self.stop()
    
    def stop(self):
        """
        Stop the TextUI and its background threads.
        """
        self.running = False
        self.ui_updater.stop()
        if self.update_thread is not None:
            self.update_thread.join(timeout=1.0)
        self._unregister_player_callbacks()
        if self.stdscr is not None:
            self.stdscr.keypad(False)
            curses.nocbreak()
            curses.echo()
            curses.endwin()
    
    def _register_player_callbacks(self):
        """
        Register callbacks for player events
        """
        # Register callbacks with the AudioController
        self.audio_controller.add_listener(EventType.PLAYER_STATE_CHANGE, self._on_player_state_change)
        self.audio_controller.add_listener(EventType.SONG_CHANGE, self._on_song_change)
        self.audio_controller.add_listener(EventType.VOLUME_CHANGE, self._on_volume_change)
        self.audio_controller.add_listener(EventType.POSITION_CHANGE, self._on_position_change)
        self.audio_controller.add_listener(EventType.CAPABILITY_CHANGE, self._on_capability_change)
    
    def _unregister_player_callbacks(self):
        """
        Unregister all callbacks
        """
        # Unregister callbacks from the AudioController
        self.audio_controller.remove_listener(EventType.PLAYER_STATE_CHANGE, self._on_player_state_change)
        self.audio_controller.remove_listener(EventType.SONG_CHANGE, self._on_song_change)
        self.audio_controller.remove_listener(EventType.VOLUME_CHANGE, self._on_volume_change)
        self.audio_controller.remove_listener(EventType.POSITION_CHANGE, self._on_position_change)
        self.audio_controller.remove_listener(EventType.CAPABILITY_CHANGE, self._on_capability_change)
    
    def _on_player_state_change(self, player: Player) -> None:
        """
        Callback for player state changes
        
        Args:
            player: Updated player information
        """
        # Only update if this is the active player
        if self.audio_controller.active_controller_id == player.player_id:
            logger.debug(f"Player state changed: {player.state}")
            self.current_player = player
            self._update_capabilities()  # Update capabilities when player state changes
            # Force a screen update
            self._request_screen_update()
    
    def _on_song_change(self, song: Optional[Song]) -> None:
        """
        Callback for song changes
        
        Args:
            song: New song information
        """
        logger.debug(f"Song changed: {song.title if song else 'None'}")
        self.current_song = song
        self._update_capabilities()  # Update capabilities when song changes
        # Force a screen update
        self._request_screen_update()
    
    def _on_volume_change(self, volume: int) -> None:
        """
        Callback for volume changes
        
        Args:
            volume: New volume level
        """
        logger.debug(f"Volume changed: {volume}")
        self.current_volume = volume
        # Force a screen update
        self._request_screen_update()
    
    def _on_position_change(self, position: Optional[float]) -> None:
        """
        Callback for position changes
        
        Args:
            position: New playback position
        """
        self.current_position = position
        # Force a screen update
        self._request_screen_update()
    
    def _on_capability_change(self, capabilities: List[str]) -> None:
        """
        Callback for capability changes.

        Args:
            capabilities: List of updated capabilities.
        """
        logger.debug(f"Capabilities changed: {capabilities}")
        # Update the UI to reflect the new capabilities
        self._update_capabilities(capabilities)
        self._request_screen_update()
    
    def _update_capabilities(self, capabilities: Optional[List[str]] = None):
        """
        Update the capabilities of the current player and adjust the UI accordingly.
        
        Args:
            capabilities: Optional list of updated capabilities. If not provided,
                          capabilities will be checked from the audio_controller.
        """
        if capabilities is not None:
            # Use the provided capabilities directly
            self.can_next = PlayerController.CAP_NEXT in capabilities
            self.can_previous = PlayerController.CAP_PREVIOUS in capabilities
        elif self.current_player:
            # Get capabilities from the audio controller
            self.can_next = self.audio_controller.can_next()
            self.can_previous = self.audio_controller.can_previous()
        else:
            self.can_next = False
            self.can_previous = False
    
    def _request_screen_update(self):
        """
        Request a screen update
        
        This method is called from callbacks that run in different threads.
        It marks that an update is needed, which the main loop will detect.
        """
        # Thread-safely update the last update request timestamp
        with self.update_lock:
            self.last_update_request = time.time()
    
    def _main_loop(self):
        """
        Main UI loop - handle keypresses and refresh display
        """
        last_draw_time = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                # Check if an update has been requested since the last draw
                update_needed = False
                with self.update_lock:
                    if self.last_update_request > last_draw_time:
                        update_needed = True
                
                # Draw the screen if:
                # 1. An update has been requested, or
                # 2. It's been at least 0.5 seconds since the last draw (periodic refresh)
                if update_needed or (current_time - last_draw_time) >= 0.5:
                    self._draw_screen()
                    last_draw_time = current_time
                
                # Handle keypress (this has a built-in timeout)
                self._handle_keypress()
                
                # Small sleep to prevent 100% CPU usage
                time.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Error in UI main loop: {e}")
                self.show_message(f"Error: {e}")
    
    def _update_info_thread(self):
        """
        Background thread to periodically update player information
        
        This is now less important as we get most updates via callbacks,
        but we keep it as a backup for controllers that don't send updates
        or for information not provided by callbacks.
        """
        while self.running:
            try:
                # Update player info - now less frequently as we get most updates via callbacks
                active_player = self.audio_controller.get_active_player_info()
                
                # Only update if we have a new active player or controller doesn't support callbacks
                if not self.current_player or active_player.player_id != self.current_player.player_id:
                    self.current_player = active_player
                    self.current_song = self.audio_controller.get_current_song()
                    self.current_volume = self.audio_controller.get_volume() or 0
                    self.current_position = self.audio_controller.get_position()
                
            except Exception as e:
                logger.error(f"Error updating player info: {e}")
                
            # Sleep for 2 seconds (slower updates now that we have callbacks)
            time.sleep(2.0)
    
    def _handle_keypress(self):
        """
        Handle keyboard input
        """
        try:
            key = self.stdscr.getch()
            if key == -1:  # No key pressed
                return

            if key == self.KEY_QUIT:
                self.running = False
            elif key == self.KEY_PLAY or key == self.KEY_PAUSE:
                # Toggle between play and pause
                if self.current_player and self.current_player.state == PlayerState.PLAYING:
                    self.audio_controller.pause()
                    self.show_message("Pause")
                else:
                    self.audio_controller.play()
                    self.show_message("Play")
            elif key == self.KEY_STOP:
                self.audio_controller.stop()
                self.show_message("Stop")
            elif key == self.KEY_NEXT and self.can_next:
                self.audio_controller.next()
                self.show_message("Next track")
            elif key == self.KEY_PREV and self.can_previous:
                self.audio_controller.previous()
                self.show_message("Previous track")
            elif key == self.KEY_VOLUME_UP:
                new_vol = min(100, (self.current_volume or 0) + 5)
                self.audio_controller.set_volume(new_vol)
                self.show_message(f"Volume: {new_vol}%")
            elif key == self.KEY_VOLUME_DOWN:
                new_vol = max(0, (self.current_volume or 0) - 5)
                self.audio_controller.set_volume(new_vol)
                self.show_message(f"Volume: {new_vol}%")
            elif key == self.KEY_MUTE:
                is_muted = self.audio_controller.is_muted()
                if is_muted is not None:
                    self.audio_controller.mute(not is_muted)
                    self.show_message(f"{'Muted' if not is_muted else 'Unmuted'}")
            elif key == self.KEY_SHUFFLE:
                shuffle = self.audio_controller.get_shuffle()
                if shuffle is not None:
                    self.audio_controller.set_shuffle(not shuffle)
                    self.show_message(f"Shuffle {'on' if not shuffle else 'off'}")
            elif key == self.KEY_LOOP:
                # Cycle through loop modes
                from ac3.player.player_controller import LoopMode
                current_mode = self.audio_controller.get_loop_mode()
                if current_mode == LoopMode.NONE:
                    new_mode = LoopMode.TRACK
                    mode_name = "Track"
                elif current_mode == LoopMode.TRACK:
                    new_mode = LoopMode.PLAYLIST
                    mode_name = "Playlist"
                else:
                    new_mode = LoopMode.NONE
                    mode_name = "Off"
                self.audio_controller.set_loop_mode(new_mode)
                self.show_message(f"Loop mode: {mode_name}")
            elif key == self.KEY_SEEK_FWD:
                # Seek forward 10 seconds
                pos = self.current_position
                if pos is not None:
                    self.audio_controller.seek(pos + 10)
                    self.show_message("Seek +10s")
            elif key == self.KEY_SEEK_BACK:
                # Seek backward 10 seconds
                pos = self.current_position
                if pos is not None:
                    self.audio_controller.seek(max(0, pos - 10))
                    self.show_message("Seek -10s")
            elif key == self.KEY_SWITCH_CONTROLLER:
                # Show available controllers and let user switch
                self._show_controller_selection()
        except Exception as e:
            logger.error(f"Error handling keypress: {e}")
            self.show_message(f"Error: {e}")
    
    def _show_controller_selection(self):
        """
        Show a menu to select an active controller
        """
        # When switching controllers, we need to update our callbacks
        old_controllers = set(controller for controller, _, _ in self.registered_callbacks)
        
        controllers = self.audio_controller.get_controllers()
        if not controllers:
            self.show_message("No controllers available")
            return
            
        # Clear screen
        self.stdscr.clear()
        
        # Draw header
        self.stdscr.addstr(0, 0, "Available Controllers", curses.A_BOLD)
        self.stdscr.addstr(1, 0, "Press number to select, ESC to cancel")
        
        # Draw controllers
        for i, controller in enumerate(controllers):
            line = 3 + i
            active = controller.player_id == self.audio_controller.active_controller_id
            prefix = "* " if active else "  "
            self.stdscr.addstr(line, 0, f"{i+1}. {prefix}{controller.name} ({controller.player_id})")
        
        self.stdscr.refresh()
        
        # Wait for selection
        while True:
            key = self.stdscr.getch()
            if key == 27:  # ESC
                break
                
            # Check for number keys 1-9
            if ord('1') <= key <= ord('9'):
                idx = key - ord('1')
                if idx < len(controllers):
                    controller = controllers[idx]
                    self.audio_controller.set_active_controller(controller.player_id)
                    
                    # Update our callbacks if we have new controllers
                    new_controllers = set(controllers)
                    if new_controllers != old_controllers:
                        self._unregister_player_callbacks()
                        self._register_player_callbacks()
                    
                    self.show_message(f"Switched to {controller.name}")
                    break
    
    def _format_time(self, seconds: Optional[float]) -> str:
        """
        Format time in seconds to MM:SS format
        
        Args:
            seconds: Time in seconds, or None
            
        Returns:
            Formatted time string, or '--:--' if None
        """
        if seconds is None:
            return "--:--"
        
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes:02d}:{secs:02d}"
    
    def show_message(self, message: str, timeout: float = 3.0):
        """
        Show a temporary message
        
        Args:
            message: Message to display
            timeout: Time in seconds to show the message
        """
        self.message = message
        self.message_timeout = time.time() + timeout
    
    def _draw_screen(self):
        """
        Draw the UI screen
        """
        if not self.stdscr:
            return
            
        # Get terminal dimensions
        height, width = self.stdscr.getmaxyx()
        
        # Clear screen
        self.stdscr.clear()
        
        # Header
        header = "AudioControl3 Text UI"
        self.stdscr.addstr(0, (width - len(header)) // 2, header, curses.A_BOLD)
        
        # Player info
        player_line = 2
        if self.current_player:
            player_name = f"Player: {self.current_player.name} ({self.current_player.state})"
            self.stdscr.addstr(player_line, 0, player_name)
        else:
            self.stdscr.addstr(player_line, 0, "No active player")
        
        # Volume
        volume_text = f"Volume: {self.current_volume}%"
        self.stdscr.addstr(player_line, width - len(volume_text) - 1, volume_text)
        
        # Song info
        song_line = 4
        if self.current_song:
            # Title
            if self.current_song.title:
                title = f"Title: {self.current_song.title}"
                self.stdscr.addstr(song_line, 0, title[:width-1])
                
            # Artist
            if self.current_song.artist:
                artist = f"Artist: {self.current_song.artist}"
                self.stdscr.addstr(song_line + 1, 0, artist[:width-1])
                
            # Album
            if self.current_song.album:
                album = f"Album: {self.current_song.album}"
                self.stdscr.addstr(song_line + 2, 0, album[:width-1])
        else:
            self.stdscr.addstr(song_line, 0, "No song playing")
        
        # Position/progress
        position_line = 8
        if self.current_song and self.current_position is not None:
            pos_str = self._format_time(self.current_position)
            length_str = self._format_time(self.current_song.duration)
            position_text = f"Position: {pos_str} / {length_str}"
            self.stdscr.addstr(position_line, 0, position_text)
            
            # Progress bar
            if self.current_song.duration:
                progress_width = width - 4
                pos_percent = min(1.0, max(0.0, self.current_position / self.current_song.duration))
                filled = int(progress_width * pos_percent)
                
                self.stdscr.addstr(position_line + 1, 0, "[")
                self.stdscr.addstr(position_line + 1, 1, "=" * filled)
                self.stdscr.addstr(position_line + 1, 1 + filled, " " * (progress_width - filled))
                self.stdscr.addstr(position_line + 1, 1 + progress_width, "]")
        
        # Controls help
        help_line = height - 6
        self.stdscr.addstr(help_line, 0, "Controls:", curses.A_BOLD)
        next_text = "n: Next" if self.can_next else "n: Next (disabled)"
        prev_text = "p: Previous" if self.can_previous else "p: Previous (disabled)"
        self.stdscr.addstr(help_line + 1, 0, f"Space: Play/Pause  s: Stop  {next_text}  {prev_text}")
        self.stdscr.addstr(help_line + 2, 0, "+/-: Volume  m: Mute  r: Shuffle  l: Loop")
        self.stdscr.addstr(help_line + 3, 0, "Left/Right: Seek  c: Switch Controller  q: Quit")
        
        # Message (if any)
        if self.message and time.time() < self.message_timeout:
            msg_line = height - 1
            self.stdscr.addstr(msg_line, 0, self.message, curses.A_BOLD)
        
        # Refresh the screen
        self.stdscr.refresh()

def run_textui(audio_controller: AudioController):
    """
    Run the text UI
    
    Args:
        audio_controller: The AudioController instance to control
    """
    ui = TextUI(audio_controller)
    ui.start()


if __name__ == "__main__":
    # Example of how to use the TextUI
    import sys
    from ac3.audio_controller import AudioController
    
    # Create an audio controller
    controller = AudioController()
    
    # Try to load available controllers
    from ac3.player.player_controller import PlayerController
    
    # Get available controller types
    controller_types = PlayerController.controllerImplementations()
    if not controller_types:
        print("No player controllers available")
        sys.exit(1)
    
    # Create and register controllers
    for controller_type in controller_types:
        player_controller = PlayerController.createController(controller_type)
        if player_controller:
            controller.register_controller(player_controller)
    
    # Start the UI
    run_textui(controller)