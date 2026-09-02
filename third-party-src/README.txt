KVRouite - Corresponding Source Archive
=======================================

KVRouite itself is published under the GNU General Public License, version 3
or later. Its own source code is at
https://github.com/ridewithoutstomach/KVRouite

This archive holds the corresponding source for the FFmpeg and mpv binaries
that were distributed together with KVRouite (named VGSync until October
2025). The binaries themselves are no longer distributed. This source is kept
available for the people who received them.


WHICH FILE BELONGS TO WHICH VERSION
-----------------------------------

Up to version 3.25 (2025-03-16)
  These versions shipped FFmpeg and libmpv as shared libraries, compiled by
  the author himself in an LGPL configuration.

  FFmpeg "N-118448-g43be8d0728", compiled 2025-02-09
    source        -> ffmpeg-source_43be8d0728_LGPL.zip
    upstream commit  43be8d07281caca2e88bfd8ee2333633e1fb1a13 (2025-02-08)
    build details -> LGPL-era-BUILDINFO.txt
    license          LGPL-2.1-or-later

  libmpv, built with meson -Dgpl=false
    The exact revision could not be reconstructed, so both candidates are here:
    source (a)    -> mpv-source_0.39.0_LGPL-era.zip
                     release 0.39.0, current at the time of the build
    source (b)    -> mpv-source_master-2025-02-08_LGPL-era.zip
                     master at commit e4b64fba9c5c6ca97189f32c056d05c2b47cebd6
    build details -> LGPL-era-BUILDINFO.txt
    license          LGPL-2.1-or-later

Version 3.27 (2025-04-04) through 5.01 (2026-08-28)
  These versions shipped third-party builds. KVRouite compiled neither of
  them; both are the upstream projects' own builds, redistributed unchanged.

  FFmpeg 7.1 (gyan.dev full_build, static, GPL configuration)
    ffmpeg.exe sha256
      36a59b638b49f8e6c622f4de7c4c8aaf8442f30138a58882ee2af3f410e5fd5c
    source        -> ffmpeg-source_7.1.zip
    upstream commit  b08d7969c550a804a59511c7b83f2dd8cc0499b8 (release n7.1)
    build details -> ffmpeg-7.1-BUILDINFO.txt
    license          GPL-3.0-or-later

  libmpv, build "mpv v0.39.0-1025-g6c4218252", built 2025-03-16 by shinchiro
    This is a nightly build, NOT release 0.40.0.
    source        -> mpv-source_6c4218252.zip
    upstream commit  6c4218252278c582c7a40654c66f8216aac43326 (2025-03-15)
    build scripts -> mpv-winbuild-cmake_b41d3cb.zip
                     (shinchiro/mpv-winbuild-cmake at b41d3cb259d3, the last
                      commit before the build)
    license          GPL-2.0-or-later

Version 6.0 (2026-08-30) and later
  These versions ship neither FFmpeg nor mpv. Playback and export run on
  GStreamer / GStreamer Editing Services. The corresponding source for the
  GStreamer and Qt components is named inside the application itself, in
  _internal/gstreamer/CORRESPONDING-SOURCE.txt and
  _internal/qt/CORRESPONDING-SOURCE.txt.


IF SOMETHING HERE IS MISSING OR DOES NOT MATCH
----------------------------------------------

Write to bernd@kvrouite.com and say which version of KVRouite or VGSync you
received. You will be sent a working source for that exact binary. This offer
is valid for at least three years from the date you received the software and
is extended to anyone who receives it.
