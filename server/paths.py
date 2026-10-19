"""Filesystem locations for the Lectern server.

Everything is resolved relative to BASE_PATH, the repository root.
"""
import os


def get_base_path():
    # This file lives in server/, so the repo root is one level up.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_PATH = get_base_path()

STATIC_DIR = os.path.join(BASE_PATH, 'static')
TEMPLATES_DIR = os.path.join(BASE_PATH, 'templates')

# The three builders, as single HTML files. Lectern serves them scoped
# (see tools.py); each file also still opens on its own in a browser.
TOOLS_DIR = os.path.join(BASE_PATH, 'tools')
