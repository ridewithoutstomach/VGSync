KVRouite
======

> **Note:** This project was **formerly known as [VGSync](https://github.com/ridewithoutstomach/VGSync)**.  
> The name was changed to better reflect the tool’s purpose — it’s much more than a sync utility:  
> a complete *Video and GPX Route Creation Suite*.

![Kinomap Logo](./doc/Kinomap_Logo.png)

KVRouite is a Python-based desktop application designed to synchronize GPX data with video footage. Its a Video and GPX synchronising tool. It uses "mpv" for high-precision video playback and "ffmpeg" for media processing. From version 6.0 on, the timeline can optionally be played through "GStreamer Editing Services (GES)" instead of mpv.

![KVRouite Main Window](./screenshots/mainwindow.png)

- Version: see Releases
- Platforms: Windows 64-bit (official support), Linux (tested on Kubuntu 24.04.2)
- License: GNU General Public License v3.0 or later (GPL-3.0-or-later)
- KVRouite helps action cam users and outdoor enthusiasts to synchronize their recorded videos with GPS data for perfect route visualization and editing.
-------------------------------------------------------------------------------

Requirements
------------

- Python 3.10.9 (64-bit) or Python 3.12.0 (64-bit)
- mpv binary (must be placed in "mpv/" folder)
- ffmpeg binary (must be placed in "ffmpeg/" folder)

Python packages are split into two files:

- "requirements.txt" - everything the application needs to run.
  The same list on Linux and Windows.
- "requirements-ges.txt" - optional, Windows/macOS only: the GStreamer runtime
  for the GES video backend. On Linux this comes from the distribution instead.
- "requirements-build.txt" - additional packages needed only to build the
  Windows executable (PyInstaller and its dependencies).

If you just want to run KVRouite, "requirements.txt" is all you need.

Note:
Binaries are NOT included in the Git repository due to size limitations.
You must manually download and extract them from the GitHub Releases page.

-------------------------------------------------------------------------------
## 🔧 Installation & Usage (Linux & Windows)

---

### 🐧 Linux

#### Requirements

Install the required system packages (one-time setup):

```bash
sudo apt update
sudo apt install ffmpeg libmpv-dev python3-venv
```

#### Optional: GES video backend (6.0)

From 6.0 on, KVRouite can play the timeline through GStreamer Editing
Services instead of mpv, which makes crossfades visible in the preview.
mpv stays the default -- skip this section if you do not need it.

On Linux there are no GStreamer Python wheels, so this comes from the
distribution:

```bash
sudo apt install python3-gi python3-gi-cairo \
    gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gir1.2-ges-1.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav gstreamer1.0-gl gstreamer1.0-x
```

`gir1.2-ges-1.0` is in the *universe* component; if apt cannot find it,
enable it once with `sudo add-apt-repository universe`. Ubuntu 24.04 LTS
ships GStreamer 1.24.2, Ubuntu 26.04 LTS ships 1.28.2; the Windows build
uses the 1.28.6 wheels (see `requirements-ges.txt`).

These are **system** packages. A plain venv hides them and `import gi`
fails although everything is installed -- create the venv with
`--system-site-packages` as shown below.

Then verify the environment before starting the app:

```bash
python3 check_ges.py
```

It checks typelibs, the GES engine, a usable video sink, an H.264 decoder
and ffmpeg, and names the missing package instead of failing later inside
the player. Switch the backend in the app under Config -> Video Backend;
it takes effect after a restart.

A step-by-step guide with a troubleshooting table is in
[`GES_Installation_Kubuntu.md`](GES_Installation_Kubuntu.md) (German).

#### Download the Project

You can **either**:

- Download the latest ZIP from [GitHub Releases](https://github.com/ridewithoutstomach/KVRouite/releases) and extract it  
**or**
- Clone the repository:

```bash
git clone https://github.com/ridewithoutstomach/KVRouite.git
```

#### Setup and Run

```bash
cd KVRouite
python3 -m venv venv                            # with the GES backend:
# python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt
python KVRouite.py
```

---

### 🪟 Windows


#### Setup and Run

Open **Command Prompt**, then:

```cmd
cd KVRouite
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python KVRouite.py
```

---

#### Optional: GES video backend (6.0)

On Windows the whole GStreamer runtime comes as pip wheels - no MSYS2, no
system installation:

```cmd
pip install -r requirements-ges.txt
```

That installs `gstreamer-bundle` 1.28.6 (~80 MB in site-packages; uninstalling
removes every file). mpv stays the default; switch under Config -> Video
Backend, it takes effect after a restart.

Licensing note: these wheels contain GPL- and LGPL-licensed binaries, among
them the x264/x265 encoder plugins that the GES encoder renders with. **If you
build and redistribute a Windows executable yourself, you are redistributing
those binaries** and the obligations in `gstreamer/NOTICE.txt` apply to you.
In practice that means shipping the license texts and keeping the directions to
the sources next to them - not hosting sources yourself, since the binaries are
the GStreamer Project's own and their sources are published by that project
(see `gstreamer/CORRESPONDING-SOURCE.txt`). `build_with_pyinstaller.py` copies
`gstreamer/` into the build for you and prints whether the GStreamer runtime
actually ended up in it.

---

### ❗ Important Notes

- Always create and activate the virtual environment **inside** the `KVRouite` folder.
- Do **not** run `python KVRouite.py` outside the project folder.
- On **Linux**, make sure required packages like `ffmpeg` and `libmpv-dev` are installed.



-------------------------------------------------------------------------------

Install External Binaries (Windows)
--------------------------

Download the following ZIP files from the latest KVRouite Release:

- ffmpeg.zip → extract into "ffmpeg/" folder
- mpv.zip → extract into "mpv/" folder

The "ffmpeg/" and "mpv/" folders include guidance files ("KVRouite_ffmpeg.txt" and "KVRouite_mpv.txt") describing the expected contents.

There is no ZIP for GStreamer: it is installed with `pip install -r requirements-ges.txt`
(see above). The "gstreamer/" folder in this repository contains no binaries - only the
license texts, the component list and the source code offer, which the build process
copies next to the runtime.

-------------------------------------------------------------------------------

Running the Application
------------------------

To start KVRouite:

    python KVRouite.py

Important for Linux users:
After launching the application, please enable "Use Software OpenGL" 
in the Config menu to ensure proper video playback.

-------------------------------------------------------------------------------

Windows Executable
------------------

If you prefer not to install Python or manage dependencies manually,
you can use the pre-built Windows binary:

1. Download the ZIP file (e.g., "KVRouite_3.27_Win_x64.zip") from the GitHub Releases page.
2. Extract the ZIP file into any folder.
3. Double-click "KVRouite.exe" to run the application.

-------------------------------------------------------------------------------

Building the Windows Executable Manually
----------------------------------------

To create your own Windows executable, install the build packages on top of
the runtime ones:

    pip install -r requirements.txt
    pip install -r requirements-build.txt
    python build_with_pyinstaller.py

The resulting executable will be located at:

    dist/KVRouite_3.27/KVRouite.exe

-------------------------------------------------------------------------------

Third-Party Components
-----------------------

This project includes and relies on the following third-party components:

FFmpeg
- Version: 7.1-full_build
- License: GPL-3.0-or-later (this build is configured with --enable-gpl)
- Website: https://ffmpeg.org
- Binaries provided in: "ffmpeg/"
- Original source code included in: "third-party-src/ffmpeg-source_7.1.zip"
- Notice and source code offer: "ffmpeg/NOTICE.txt"

mpv / libmpv
- Version: 0.40.0
- License: GPL-2.0-or-later. mpv is LGPLv2.1+ only when built without any
  GPL-only files; the libmpv-2.dll shipped here links libx264 and libx265 and
  is therefore a GPL build.
- Website: https://mpv.io
- Binaries provided in: "mpv/"
- Original source code included in: "third-party-src/mpv-0.40.0-source.zip"
- Notice and source code offer: "mpv/NOTICE.txt"

GStreamer / GStreamer Editing Services (GES)
- Version: 1.28.6 on Windows (pip package "gstreamer-bundle", see
  requirements-ges.txt); on Linux whatever the distribution ships
- License: LGPL-2.1-or-later for GStreamer core, gst-plugins-base/good/bad,
  GES and PyGObject. The bundled x264 and x265 encoder plugins - which the GES
  encoder uses for rendering - and the a52dec/dtsdec/dvdread plugins are
  GPL-2.0-or-later. Further components are under MIT, BSD, Apache-2.0, MPL and
  other permissive licenses. The Microsoft Visual C++ runtime redistributables
  contained in the wheels are proprietary Microsoft components and are System
  Libraries in the sense of the GNU GPL.
- Website: https://gstreamer.freedesktop.org
- Binaries: **Windows only.** They are installed by pip and are placed into the
  "_internal" folder of the Windows build. **On Linux nothing of this is
  distributed with KVRouite** - GStreamer is installed from the distribution's
  own packages, so KVRouite redistributes no GStreamer binary there.
- Source code: the binaries are the GStreamer Project's own prebuilt wheels,
  passed on unchanged. KVRouite compiles nothing here, so there is no KVRouite
  build to publish - the Corresponding Source is the 1.28.6 release tarballs at
  https://gstreamer.freedesktop.org/src/ plus the project's cerbero build
  recipes. GPLv3 section 6(d) permits exactly this: source on a third-party
  server, with clear directions next to the binaries. Those directions, the
  individual tarball URLs and a fallback contact are in
  "gstreamer/CORRESPONDING-SOURCE.txt".
- Notice and per-package license list: "gstreamer/NOTICE.txt" and
  "gstreamer/COMPONENTS.txt" (in the Windows build: "_internal/gstreamer/")
- Note: KVRouite ships FFmpeg twice. The "ffmpeg/" folder holds the GPL
  full build used for cutting and rendering; the GStreamer wheels contain an
  independent LGPL build of the FFmpeg libraries used by the gst-libav plugin.

GoPro GPS Extraction
- Based on: gopro2gpx by Juan M. Casillas (https://github.com/juanmcasillas/gopro2gpx)
- Modifications by: Bernd Eller
- License: GNU GPL v3

KVRouite as a whole is distributed under GPL-3.0-or-later. All of the above are
compatible with that: GPL-2.0-or-later and LGPL-2.1-or-later both allow use
under any later version of the respective license.

All third-party components are redistributed in accordance with their respective
licenses.

For FFmpeg and mpv the complete and unmodified source code is included in the
"third-party-src/" directory and offered at https://kvrouite.com/downloads/index.php.

For GStreamer it is not, and does not need to be: those binaries are the
GStreamer Project's own, redistributed unchanged, and their Corresponding Source
is published by that project in the same version - see
"gstreamer/CORRESPONDING-SOURCE.txt" for the exact URLs and the reasoning.

Either way, sources will be made available for at least three (3) years in
accordance with GPL and LGPL requirements. Requests can be sent to
bernd@kvrouite.com.

None of these components are modified by KVRouite. All libraries are loaded
dynamically from separate files and can be replaced by your own builds
(LGPL section 6): overwrite the corresponding DLL in the "_internal" folder and
restart the application. The Windows build is deliberately not packed into a
single-file executable, so that this stays possible.


-------------------------------------------------------------------------------

License
-------

This project is licensed under the GNU General Public License v3.0 or later.

You are free to:
- Use, copy, and distribute this software
- Study and modify the source code
- Redistribute modified versions under the same license

The full text of the license is included in the "LICENSE" file.

-------------------------------------------------------------------------------

Contact
-------

For questions, suggestions, or contributions, please open an issue or pull request on GitHub.

-------------------------------------------------------------------------------

## Legal / Contact

Project: **KVRouite — Kinomap Video Route Suite** (officially supported by Kinomap)

**Imprint (DE):** https://kvrouite.com/impressum.html  
**Privacy:** https://kvrouite.com/privacy.html

No cookies/trackers are set on the project website beyond what is technically necessary.  
GitHub may process connection data per their Privacy Statement.  
For contact, please use GitHub Issues or the email button on the imprint page.