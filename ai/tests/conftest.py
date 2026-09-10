import sys
from pathlib import Path

# The package lives one directory up; tests run from ai/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
