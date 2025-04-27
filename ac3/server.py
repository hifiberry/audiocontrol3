"""
AudioControl3 REST API Server
Provides a simple REST API to access information about AudioControl3
"""

from flask import Flask, jsonify, request
import logging
import json
from dataclasses import asdict
from ac3 import __version__
from ac3.metadata import Song

# Initialize logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ac3.server")

# Create Flask application
app = Flask(__name__)

# Get version from package
VERSION = __version__

# Store the currently playing song
current_song = Song(
    title="No song playing",
    artist="Unknown",
    source="none"
)


@app.route('/system-info', methods=['GET'])
def system_info():
    """Endpoint to return AudioControl3 system information"""
    logger.info("System info requested")
    return jsonify({
        "name": "AudioControl3",
        "version": VERSION,
        "status": "running"
    })



def start_server(host='0.0.0.0', port=5000, debug=False):
    """
    Start the REST API server
    
    Args:
        host: Host address to bind to
        port: Port to listen on
        debug: Whether to run in debug mode
    """
    logger.info(f"Starting AudioControl3 server on {host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    start_server(debug=True)