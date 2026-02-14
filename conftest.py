"""
conftest.py — ensures the project root is on sys.path so pytest can import
the 'core' package without an editable install.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
