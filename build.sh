#!/usr/bin/env bash
# Build standalone ProfSync wizard binary using PyInstaller

set -e

echo "Building ProfSync wizard binary..."
pyinstaller --onefile --name profsync-wizard wizard.py

echo "Build complete!"
echo "Binary location:"
echo "  Linux/macOS: ./dist/profsync-wizard"
echo "  Windows: ./dist/profsync-wizard.exe"
