#!/usr/bin/env python3
"""ProfSync wizard entry point."""

import sys
import os

# Add src/ to path so we can import wizard modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from main import main

if __name__ == "__main__":
    main()
