from pathlib import Path
import os
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
os.chdir(HERE)
sys.path.insert(0, str(ROOT))

from oa_review_gui import main


if __name__ == "__main__":
    main()
