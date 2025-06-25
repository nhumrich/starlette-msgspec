#!/bin/bash
# Installation script for starlette-msgspec

# Check if uv is available
if command -v uv &> /dev/null; then
    echo "Installing with uv..."
    uv pip install -e ".[test]"
else
    echo "Installing with pip..."
    pip install -e ".[test]"
fi

echo "Installation complete!"
echo "Run the example with: python examples/basic_app.py"