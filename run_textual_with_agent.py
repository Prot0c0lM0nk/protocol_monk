#!/usr/bin/env python3
"""
Test runner for Textual UI with agent event integration
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.textual.app import TextualUI


def main():
    """Run the Textual UI with agent integration"""
    print("Starting Textual UI for Protocol Monk...")
    print("Agent event bus integration enabled")
    print("Press Ctrl+C to quit\n")

    app = TextualUI()
    app.run()


if __name__ == "__main__":
    main()