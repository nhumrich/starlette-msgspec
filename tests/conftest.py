import sys
import os
from pathlib import Path

# Add the project root to the path so tests can import the package
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))