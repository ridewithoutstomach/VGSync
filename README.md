# VGSync

VGSync is a Python-based desktop application designed to synchronize GPX data with video footage. It uses `mpv` for high-precision video playback and `ffmpeg` for media processing.

- Version: 3.27
- Platform: Windows 64-bit only
- License: GNU General Public License v3.0 or later (GPL-3.0-or-later)

## Requirements

- Python 3.10 (64-bit)
- `mpv` binary (included in `mpv/`)
- `ffmpeg` binary (included in `ffmpeg/`)

## Installation

We strongly recommend using a Python virtual environment to isolate dependencies.

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

## Running the Applicaton:

python VGSync.py

## Building the Windows Executable

python build_with_pyinstaller.py

The resulting Exe is named:
VGSync.exe ( in the folder dist/VGSync_VERSION

## Third-Party Components

This project includes the following third-party open-source binaries:

### FFmpeg

- Version: 7.1 "Péter"
- License: GPLv3
- Website: https://ffmpeg.org
- Binaries included in: ffmpeg/
- Original source code included in: third-party-src/FFmpeg-7.1-source.zip
- Release notes are included in the source archive

### mpv

- Version: 0.40.0
- License: LGPLv2.1+
- Website: https://mpv.io
- Binaries included in: mpv/
- Original source code included in: third-party-src/mpv-0.40.0-source.zip
- Release notes are included in the source archive

All third-party components are redistributed in accordance with their respective licenses. Their original license and documentation files are provided in the corresponding folders. The complete and unmodified source code is included in the third-party-src/ directory and will be retained and made available for at least three (3) years in accordance with GPL and LGPL requirements.

## License

This project is licensed under the GNU General Public License v3.0 or later.

You are free to:

- Use, copy, and distribute this software
- Study and modify the source code
- Redistribute modified versions under the same license

The full text of the license is included in the file LICENSE.

This distribution includes the full source code of VGSync, along with all required third-party binaries and their sources, in compliance with GPL requirements.

## Contact

For questions, suggestions, or contributions, please open an issue or pull request on GitHub.
