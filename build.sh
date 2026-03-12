#!/bin/bash
# Build ProfSync Wizard as standalone executable

set -e

echo "🔨 ProfSync Wizard Build"
echo "========================"
echo

# Activate venv
echo "📦 Activating virtual environment..."
source venv/bin/activate

# Clean old builds
if [ -d "dist" ]; then
    echo "🗑️  Cleaning old build artifacts..."
    rm -rf build dist 2>/dev/null || true
fi

# Build with PyInstaller
echo "🏗️  Building executable..."
pyinstaller build.spec --clean -y

# Show result
echo
echo "✅ Build complete!"
echo
echo "📁 Output: dist/profsync-wizard"
echo
echo "To run:"
echo "  Linux/Mac:  ./dist/profsync-wizard/profsync-wizard --teststack"
echo "  Windows:    dist\\profsync-wizard\\profsync-wizard.exe --teststack"
echo
echo "Or distribute the entire 'dist/profsync-wizard/' folder."
