"""Put this experiment directory on sys.path so `tools` imports resolve.

Scoped to this experiment; it does not affect the repository's own test config.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
