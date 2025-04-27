"""
AutoPause Plugin

This plugin automatically pauses other players when a player starts playing.
It's useful to avoid having multiple audio sources playing simultaneously.
"""

import logging
from ac3.addons.plugin import Plugin
from ac3.player.player_controller import PlayerState

logger = logging.getLogger("ac3.plugins.autopause")

class AutoPausePlugin(Plugin):
    """
    Plugin that automatically pauses other players when a player starts playing
    """
    
    def __init__(self):
        """Initialize the AutoPause plugin"""
        super().__init__()
        self._enabled = False
    
    @property
    def name(self) -> str:
        """Get the name of the plugin"""
        return "AutoPause"
    
    @property
    def description(self) -> str:
        """Get a description of the plugin"""
        return "Automatically pauses other players when a player starts playing"
    
    @property
    def version(self) -> str:
        """Get the version of the plugin"""
        return "1.0.0"
    
    def _enable_plugin(self) -> bool:
        """Enable the plugin"""
        if self._audio_controller is None:
            logger.warning("Cannot enable AutoPause plugin: no audio controller")
            return False
            
        # Register to receive player state change events
        self._audio_controller.add_listener('player_state_change', self._on_player_state_change)
        logger.info("AutoPause plugin enabled")
        return True
    
    def _disable_plugin(self) -> bool:
        """Disable the plugin"""
        if self._audio_controller is None:
            return True
            
        # Unregister from player state change events
        self._audio_controller.remove_listener('player_state_change', self._on_player_state_change)
        logger.info("AutoPause plugin disabled")
        return True
    
    def _on_player_state_change(self, player) -> None:
        """
        Handle player state changes
        
        When a player starts playing, pause all other players.
        
        Args:
            player: The player that changed state
        """
        # Only handle PLAYING state changes
        if player.state != PlayerState.PLAYING:
            return
            
        # Don't do anything if this is the active player
        if self._audio_controller.active_controller_id == player.player_id:
            return
            
        logger.info(f"Player {player.player_id} started playing, pausing other players")
        
        # Set this player as active
        self._audio_controller.set_active_controller(player.player_id)
        
        # Pause all other players
        self._pause_other_players(player.player_id)
    
    def _pause_other_players(self, active_player_id: str) -> None:
        """
        Pause all players except the specified one
        
        Args:
            active_player_id: ID of the player to keep playing
        """
        for player_id, controller in self._audio_controller._controllers.items():
            if player_id != active_player_id:
                try:
                    # Check if the player is currently playing
                    player_info = controller.get_player_info()
                    if player_info and player_info.state == PlayerState.PLAYING:
                        logger.info(f"Pausing player {player_id}")
                        controller.pause()
                except Exception as e:
                    logger.error(f"Error pausing player {player_id}: {e}")