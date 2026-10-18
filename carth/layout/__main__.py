from carth.layout.lines import *  # noqa: F403
from carth.layout.lines import show, layout
import sys
from pathlib import Path
from carth import ingest

print(show(layout(ingest.load(Path(sys.argv[1]))), int(sys.argv[2]) if len(sys.argv) > 2 else 60))
