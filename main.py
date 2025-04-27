import argparse
import os
import sys
import platform
import logging

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Add the ac3 module directory to the Python path
sys.path.append(os.path.dirname(__file__))

# Set the home directory to the ac3 module directory
os.chdir(os.path.dirname(__file__))

# Set logging level to DEBUG to capture detailed logs
logging.basicConfig(level=logging.DEBUG)

def is_running_in_debugger():
    """
    Detect if the program is running in a debugger.
    
    Returns:
        bool: True if running in a debugger, False otherwise.
    """
    # Check if trace function is set (common for most debuggers)
    if sys.gettrace() is not None:
        return True
    
    # Check for common debugger modules in loaded modules
    debugger_modules = [
        'pydevd', 'pdb', '_pydev_bundle', 'debugpy', 'ipdb',
        'PyQt5.QtCore', 'pyqtgraph'  # For IDE debuggers
    ]
    for module in debugger_modules:
        if module in sys.modules:
            return True
    
    # Check for environment variables commonly set by debuggers
    debugger_env_vars = [
        'PYTHONBREAKPOINT', 'PYDEVD_LOAD_VALUES_ASYNC', 'DEBUGPY_PROCESS_GROUP',
        'VSCODE_PID', 'JPY_PARENT_PID', 'PYCHARM_HOSTED'
    ]
    for var in debugger_env_vars:
        if os.environ.get(var):
            return True
    
    return False

def main():
    parser = argparse.ArgumentParser(description="AudioControl3 Main Program")
    parser.add_argument("--text-ui", action="store_true", help="Enable text UI")
    parser.add_argument("--auto-progress", type=float, default=0.0, 
                        help="Automatically update playback position every N seconds (0 to disable)")
    parser.add_argument("--disable-plugins", action="store_true", 
                        help="Disable loading of plugins")
    parser.add_argument("--enable-plugin", type=str, action="append", 
                        help="Enable a specific plugin by name (can be used multiple times)")
    
    # If running in a debugger, use default debug settings unless overridden by command line
    running_in_debug = is_running_in_debugger()
    if running_in_debug and len(sys.argv) == 1:  # No command-line args provided
        print("Debugger detected. Using default debug settings:")
        debug_args = ["--text-ui", "--auto-progress", "0.5"]
        print(f"  {' '.join(debug_args)}")
        args = parser.parse_args(debug_args)
    else:
        args = parser.parse_args()

    # List all available player controllers before initializing the AudioController
    from ac3.player.player_controller import PlayerController
    available_controllers = PlayerController.controllerImplementations()
    print("Available Player Controllers:")
    for controller in available_controllers:
        print(f"- {controller}")

    # Initialize the AudioController
    from ac3.audio_controller import AudioController
    audio_controller = AudioController()

    # Add all available player controllers
    audio_controller.add_all_player_controllers()
    
    # Configure auto-progress if specified
    if args.auto_progress > 0:
        audio_controller.set_auto_progress(args.auto_progress)
        print(f"Auto-progress enabled: Position will update every {args.auto_progress} seconds")
    
    # Load plugins if not disabled
    if not args.disable_plugins:
        # Load plugins from the ac3.addons package
        plugin_count = audio_controller.load_plugins()
        print(f"Loaded {plugin_count} plugins")
        
        # Enable specific plugins if requested
        if args.enable_plugin:
            for plugin_name in args.enable_plugin:
                if audio_controller.enable_plugin(plugin_name):
                    print(f"Enabled plugin: {plugin_name}")
                else:
                    print(f"Failed to enable plugin: {plugin_name}")
        else:
            # Enable AutoPause plugin by default
            if audio_controller.enable_plugin("AutoPause"):
                print("Enabled AutoPause plugin (default)")

    # If --text-ui is specified, connect the TextUI to the controller
    if args.text_ui:
        # Check if the curses module is available
        curses_available = False
        try:
            import curses
            curses_available = True
        except ImportError:
            pass
        
        if not curses_available:
            print("The text UI is not supported due to missing curses module.")
            print("You can install the curses module with:")
            if platform.system() == "Windows":
                print("pip install windows-curses")
            else:
                print("pip install curses  # or use your system's package manager")
            print("Exiting...")
            sys.exit(1)
        else:
            from ac3.ui.textui import TextUI
            text_ui = TextUI(audio_controller)
            text_ui.start()

if __name__ == "__main__":
    main()