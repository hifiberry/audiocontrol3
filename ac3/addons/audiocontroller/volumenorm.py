"""
Volume Normalization Plugin

This plugin automatically adjusts volume based on song metadata to maintain consistent
volume levels across different tracks.
"""

import logging
from typing import Dict, Any, Optional
from ac3.addons.plugin import Plugin
from ac3.metadata import Song

logger = logging.getLogger("ac3.plugins.volumenorm")

class VolumeNormalizationPlugin(Plugin):
    """
    Plugin that adjusts volume based on track metadata for consistent listening experience
    """
    
    def __init__(self):
        """Initialize the VolumeNormalization plugin"""
        super().__init__()
        self._config = {
            "enabled": True,
            "target_level": -14.0,  # Target LUFS level
            "max_adjustment": 10,    # Maximum volume adjustment in either direction
            "default_level": -18.0   # Default level for tracks without metadata
        }
    
    @property
    def name(self) -> str:
        """Get the name of the plugin"""
        return "VolumeNormalization"
    
    @property
    def description(self) -> str:
        """Get a description of the plugin"""
        return "Automatically adjusts volume based on track metadata for consistent volume levels"
    
    @property
    def version(self) -> str:
        """Get the version of the plugin"""
        return "1.0.0"
    
    def _enable_plugin(self) -> bool:
        """Enable the plugin"""
        if self._audio_controller is None:
            logger.warning("Cannot enable VolumeNormalization plugin: no audio controller")
            return False
            
        # Register to receive song change events
        self._audio_controller.add_listener('song_change', self._on_song_change)
        logger.info("VolumeNormalization plugin enabled")
        return True
    
    def _disable_plugin(self) -> bool:
        """Disable the plugin"""
        if self._audio_controller is None:
            return True
            
        # Unregister from song change events
        self._audio_controller.remove_listener('song_change', self._on_song_change)
        logger.info("VolumeNormalization plugin disabled")
        return True
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the plugin's configuration
        
        Returns:
            Dictionary of configuration options
        """
        return self._config.copy()
    
    def set_config(self, config: Dict[str, Any]) -> bool:
        """
        Set the plugin's configuration
        
        Args:
            config: Dictionary of configuration options
            
        Returns:
            True if configuration was applied successfully, False otherwise
        """
        # Validate and apply configuration
        try:
            if "target_level" in config:
                self._config["target_level"] = float(config["target_level"])
                
            if "max_adjustment" in config:
                self._config["max_adjustment"] = int(config["max_adjustment"])
                
            if "default_level" in config:
                self._config["default_level"] = float(config["default_level"])
                
            if "enabled" in config:
                self._config["enabled"] = bool(config["enabled"])
                
            logger.info(f"VolumeNormalization configuration updated: {self._config}")
            return True
        
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid configuration value: {e}")
            return False
    
    def _on_song_change(self, song: Optional[Song]) -> None:
        """
        Handle song changes
        
        Adjusts the volume based on the song's ReplayGain or LUFS metadata.
        
        Args:
            song: The new song, or None if playback stopped
        """
        if not song or not self._config["enabled"]:
            return
            
        # Calculate adjustment based on metadata
        adjustment = self._calculate_volume_adjustment(song)
        if adjustment == 0:
            return  # No adjustment needed
            
        # Get current volume
        current_volume = self._audio_controller.get_volume()
        if current_volume is None:
            logger.warning("Cannot get current volume, skipping adjustment")
            return
            
        # Calculate new volume
        new_volume = max(0, min(100, current_volume + adjustment))
        
        # Apply new volume if it's different from current
        if new_volume != current_volume:
            logger.info(f"Adjusting volume from {current_volume} to {new_volume} for song: {song.title}")
            self._audio_controller.set_volume(new_volume)
    
    def _calculate_volume_adjustment(self, song: Song) -> int:
        """
        Calculate volume adjustment based on song metadata
        
        Args:
            song: The song to calculate adjustment for
            
        Returns:
            Volume adjustment in percentage points (-100 to 100)
        """
        # Get target level from config
        target_level = self._config["target_level"]
        max_adjustment = self._config["max_adjustment"]
        default_level = self._config["default_level"]
        
        # Try to get volume normalization info from metadata
        metadata = song.metadata if song.metadata else {}
        
        # Check for ReplayGain
        track_gain = metadata.get("replaygain_track_gain")
        if track_gain is not None:
            try:
                # ReplayGain is in dB, parse it
                if isinstance(track_gain, str):
                    # Strip "dB" suffix if present
                    track_gain = track_gain.replace("dB", "").strip()
                    gain_db = float(track_gain)
                else:
                    gain_db = float(track_gain)
                    
                # Calculate adjustment (-6dB ~= half volume, +6dB ~= double volume)
                # Adjust to target level
                level_diff = target_level - (-18.0 + gain_db)  # ReplayGain reference is -18 LUFS
                # Convert to percentage points (approximate mapping)
                adjustment = int(level_diff * 2.5)  # ~2.5% per dB
                
                logger.debug(f"ReplayGain: {gain_db}dB, adjustment: {adjustment}%")
                return max(-max_adjustment, min(max_adjustment, adjustment))
            except (ValueError, TypeError):
                logger.warning(f"Invalid ReplayGain value: {track_gain}")
        
        # Check for LUFS/integrated loudness
        loudness = metadata.get("LUFS") or metadata.get("integrated_loudness")
        if loudness is not None:
            try:
                if isinstance(loudness, str):
                    # Strip "LUFS" suffix if present
                    loudness = loudness.replace("LUFS", "").strip()
                    lufs = float(loudness)
                else:
                    lufs = float(loudness)
                    
                # Calculate adjustment
                level_diff = target_level - lufs
                # Convert to percentage points (approximate mapping)
                adjustment = int(level_diff * 2.5)  # ~2.5% per dB
                
                logger.debug(f"LUFS: {lufs}, adjustment: {adjustment}%")
                return max(-max_adjustment, min(max_adjustment, adjustment))
            except (ValueError, TypeError):
                logger.warning(f"Invalid loudness value: {loudness}")
        
        # Check for album peak
        peak = metadata.get("replaygain_track_peak") or metadata.get("replaygain_album_peak")
        if peak is not None:
            try:
                if isinstance(peak, str):
                    peak_value = float(peak)
                else:
                    peak_value = float(peak)
                    
                # If peak is very high, reduce volume to avoid clipping
                if peak_value > 1.0:
                    # Calculate dB over 0
                    db_over = 20 * (peak_value / 1.0)
                    # Convert to percentage points
                    adjustment = -int(db_over * 2.5)
                    
                    logger.debug(f"Peak adjustment: {adjustment}%")
                    return max(-max_adjustment, min(max_adjustment, adjustment))
            except (ValueError, TypeError):
                logger.warning(f"Invalid peak value: {peak}")
        
        # If song has specific artists/genres that typically need adjustments
        # This is just an example of using other metadata
        artist = song.artist.lower() if song.artist else ""
        genre = song.genre.lower() if song.genre else ""
        
        # Example: Classical music is often quieter than other genres
        if "classical" in genre:
            logger.debug("Classical genre detected, increasing volume")
            return 5  # +5% volume for classical
            
        # Example: Some genres may be mastered louder
        if "metal" in genre or "rock" in genre:
            logger.debug("Rock/metal genre detected, decreasing volume")
            return -3  # -3% volume for rock/metal
        
        # No adjustment needed
        return 0