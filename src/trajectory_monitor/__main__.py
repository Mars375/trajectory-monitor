"""Allow running as: python -m trajectory_monitor"""

from .cli import main
import sys

sys.exit(main())
