"""
Default Campfires for CampfireValley

This module provides the default campfire implementations that come with CampfireValley.
These campfires handle common torch processing patterns and can be used as-is or
extended for custom functionality.
"""

from .dockmaster import DockmasterCampfire, LoaderCamper, RouterCamper, PackerCamper

__all__ = [
    'DockmasterCampfire',
    'LoaderCamper', 
    'RouterCamper',
    'PackerCamper'
]