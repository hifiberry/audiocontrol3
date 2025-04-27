"""
Plugin system for AudioControl3

This module provides base classes and utilities for creating plugins that can extend
the functionality of the AudioController.
"""

import importlib
import inspect
import logging
import os
import pkgutil
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Type

logger = logging.getLogger("ac3.plugins")

class Plugin(ABC):
    """
    Base class for all AudioController plugins
    
    Plugins can subscribe to events from the AudioController and provide additional 
    functionality without modifying the core code.
    """
    
    def __init__(self):
        """Initialize the plugin"""
        self._audio_controller = None
        self._enabled = False
        
    @property
    def name(self) -> str:
        """
        Get the name of the plugin
        
        Returns:
            The name of the plugin
        """
        # Default to the class name, but subclasses can override
        return self.__class__.__name__
    
    @property
    def description(self) -> str:
        """
        Get a description of the plugin
        
        Returns:
            A description of the plugin
        """
        # Default to the docstring, but subclasses can override
        return self.__doc__ or "No description available"
    
    @property
    def version(self) -> str:
        """
        Get the version of the plugin
        
        Returns:
            The version of the plugin
        """
        return "1.0.0"  # Default version
    
    @property
    def enabled(self) -> bool:
        """
        Check if the plugin is enabled
        
        Returns:
            True if the plugin is enabled, False otherwise
        """
        return self._enabled
    
    def enable(self) -> bool:
        """
        Enable the plugin
        
        Returns:
            True if the plugin was successfully enabled, False otherwise
        """
        if self._enabled:
            return True  # Already enabled
            
        try:
            self._enabled = self._enable_plugin()
            if self._enabled:
                logger.info(f"Plugin {self.name} enabled")
            else:
                logger.warning(f"Failed to enable plugin {self.name}")
            return self._enabled
        except Exception as e:
            logger.error(f"Error enabling plugin {self.name}: {e}")
            return False
    
    def disable(self) -> bool:
        """
        Disable the plugin
        
        Returns:
            True if the plugin was successfully disabled, False otherwise
        """
        if not self._enabled:
            return True  # Already disabled
            
        try:
            self._enabled = not self._disable_plugin()
            if not self._enabled:
                logger.info(f"Plugin {self.name} disabled")
            else:
                logger.warning(f"Failed to disable plugin {self.name}")
            return not self._enabled
        except Exception as e:
            logger.error(f"Error disabling plugin {self.name}: {e}")
            return False
    
    def set_audio_controller(self, audio_controller: Any) -> None:
        """
        Set the audio controller for this plugin
        
        Args:
            audio_controller: The AudioController instance
        """
        self._audio_controller = audio_controller
    
    def get_audio_controller(self) -> Any:
        """
        Get the audio controller for this plugin
        
        Returns:
            The AudioController instance
        """
        return self._audio_controller
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the plugin's configuration
        
        Returns:
            Dictionary of configuration options
        """
        return {}
    
    def set_config(self, config: Dict[str, Any]) -> bool:
        """
        Set the plugin's configuration
        
        Args:
            config: Dictionary of configuration options
            
        Returns:
            True if configuration was applied successfully, False otherwise
        """
        return False  # Default implementation does nothing
    
    @abstractmethod
    def _enable_plugin(self) -> bool:
        """
        Enable the plugin (implementation)
        
        This method should be implemented by subclasses to perform any setup
        needed when the plugin is enabled, such as subscribing to events.
        
        Returns:
            True if the plugin was successfully enabled, False otherwise
        """
        pass
    
    @abstractmethod
    def _disable_plugin(self) -> bool:
        """
        Disable the plugin (implementation)
        
        This method should be implemented by subclasses to perform any cleanup
        needed when the plugin is disabled, such as unsubscribing from events.
        
        Returns:
            True if the plugin was successfully disabled, False otherwise
        """
        pass


class PluginManager:
    """
    Manages the discovery, loading, and lifecycle of plugins for the AudioController
    """
    
    def __init__(self, audio_controller: Any):
        """
        Initialize the plugin manager
        
        Args:
            audio_controller: The AudioController instance to use with plugins
        """
        self._audio_controller = audio_controller
        self._plugins: Dict[str, Plugin] = {}
        self._plugin_classes: Dict[str, Type[Plugin]] = {}
        
    def discover_plugins(self, package: str = "ac3.addons") -> List[Type[Plugin]]:
        """
        Discover available plugins from the specified package
        
        Args:
            package: The package path to search for plugins
            
        Returns:
            List of discovered plugin classes
        """
        logger.info(f"Discovering plugins in package: {package}")
        discovered = []
        
        # Import the package
        try:
            pkg = importlib.import_module(package)
        except ImportError as e:
            logger.error(f"Error importing package {package}: {e}")
            return discovered
            
        # Walk through the package and subpackages
        for _, name, is_pkg in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + '.'):
            if is_pkg:
                # Recursively search subpackages
                discovered.extend(self.discover_plugins(name))
                continue
                
            # Import the module
            try:
                module = importlib.import_module(name)
                
                # Find Plugin subclasses in the module
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, Plugin) and 
                            obj != Plugin and 
                            obj.__module__ == name):
                        logger.debug(f"Discovered plugin: {obj.__name__} in {name}")
                        discovered.append(obj)
                        self._plugin_classes[obj.__name__] = obj
            except Exception as e:
                logger.error(f"Error loading module {name}: {e}")
                
        return discovered
        
    def load_plugin(self, plugin_class: Type[Plugin]) -> Optional[Plugin]:
        """
        Load a plugin by its class
        
        Args:
            plugin_class: The plugin class to instantiate
            
        Returns:
            The plugin instance, or None if loading failed
        """
        try:
            plugin = plugin_class()
            plugin.set_audio_controller(self._audio_controller)
            
            plugin_id = plugin.name
            if plugin_id in self._plugins:
                logger.warning(f"Plugin {plugin_id} is already loaded")
                return self._plugins[plugin_id]
                
            self._plugins[plugin_id] = plugin
            logger.info(f"Loaded plugin: {plugin_id}")
            return plugin
        except Exception as e:
            logger.error(f"Error loading plugin {plugin_class.__name__}: {e}")
            return None
    
    def load_plugin_by_name(self, plugin_name: str) -> Optional[Plugin]:
        """
        Load a plugin by its name
        
        Args:
            plugin_name: The name of the plugin to load
            
        Returns:
            The plugin instance, or None if loading failed
        """
        if plugin_name in self._plugins:
            return self._plugins[plugin_name]  # Already loaded
            
        if plugin_name in self._plugin_classes:
            return self.load_plugin(self._plugin_classes[plugin_name])
            
        logger.warning(f"Plugin {plugin_name} not found")
        return None
    
    def load_all_plugins(self) -> List[Plugin]:
        """
        Load all discovered plugins
        
        Returns:
            List of loaded plugin instances
        """
        loaded = []
        for plugin_class in self._plugin_classes.values():
            plugin = self.load_plugin(plugin_class)
            if plugin:
                loaded.append(plugin)
        return loaded
    
    def enable_plugin(self, plugin_id: str) -> bool:
        """
        Enable a plugin by its ID
        
        Args:
            plugin_id: The ID of the plugin to enable
            
        Returns:
            True if the plugin was enabled, False otherwise
        """
        if plugin_id not in self._plugins:
            plugin = self.load_plugin_by_name(plugin_id)
            if not plugin:
                return False
        
        return self._plugins[plugin_id].enable()
    
    def disable_plugin(self, plugin_id: str) -> bool:
        """
        Disable a plugin by its ID
        
        Args:
            plugin_id: The ID of the plugin to disable
            
        Returns:
            True if the plugin was disabled, False otherwise
        """
        if plugin_id not in self._plugins:
            return False
        return self._plugins[plugin_id].disable()
    
    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        """
        Get a plugin by its ID
        
        Args:
            plugin_id: The ID of the plugin to get
            
        Returns:
            The plugin instance, or None if not loaded
        """
        return self._plugins.get(plugin_id)
    
    def get_plugins(self) -> Dict[str, Plugin]:
        """
        Get all loaded plugins
        
        Returns:
            Dictionary mapping plugin IDs to plugin instances
        """
        return self._plugins.copy()
    
    def get_enabled_plugins(self) -> Dict[str, Plugin]:
        """
        Get all enabled plugins
        
        Returns:
            Dictionary mapping plugin IDs to plugin instances
        """
        return {
            plugin_id: plugin 
            for plugin_id, plugin in self._plugins.items() 
            if plugin.enabled
        }