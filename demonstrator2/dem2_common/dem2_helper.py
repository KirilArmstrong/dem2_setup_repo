"""Helper Script for Demonstrator 2."""
import os
from demonstrator2.__globals__ import __configpath__, __datapath__


def setup_directories():
    """Setup config and data directories for development and testing."""
    if not os.path.exists(__configpath__):
        os.makedirs(__configpath__)
    if not os.path.exists(__datapath__):
        os.makedirs(__datapath__)