# OA Review macOS notes

Windows `OA_Review.exe` cannot be converted directly into a native macOS app. Use one of the two macOS entry points below.

## Run A1689 with Python

Copy the full `Astronaut_OA` folder to the Mac, then run:

```bash
cd /path/to/Astronaut_OA
python3 -m venv .venv-oa-review
source .venv-oa-review/bin/activate
python -m pip install -r requirements-oa-review.txt
chmod +x A1689/OA_Review.command
open A1689/OA_Review.command
```

## Build a macOS app

PyInstaller must be run on macOS:

```bash
cd /path/to/Astronaut_OA
bash build_macos.sh A1689
open A1689/OA_Review.app
```

`OA_Review.app` should be placed inside the same cluster folder as `vis_table.csv` and `annotation_check_triplets`.
