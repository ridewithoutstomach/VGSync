# Changelog

All notable changes to KVRouite are listed here, newest version first.
The section of a version is also the text that goes into the GitHub release notes.

Versions up to and including 5.0 are documented in the GitHub releases only.

---

## 6.0 – unreleased

### Removed

**ffmpeg is no longer shipped — copy mode uses yours**

Rendering moved to GES, so the FFmpeg full build in `ffmpeg/` (435 MB) was
only still needed by copy mode, which cuts on keyframes with `-c copy`. It is
no longer distributed:

- `build_with_pyinstaller.py` does not copy `ffmpeg/` into the build any more.
  A new `check_ffmpeg_frei()` runs before packing and aborts if an `ffmpeg`
  folder or an ffmpeg/ffprobe/ffplay executable turns up in it. It deliberately
  ignores `av*.dll` — the GStreamer wheels bring their own **LGPL** FFmpeg
  libraries for gst-libav, and those stay.
- Copy mode is greyed out unless **both** `ffmpeg` and `ffprobe` are in your
  PATH. It used to check only `ffmpeg`, so having just one of them led into a
  mode that failed at export. KVRouite now also says once at startup what is
  missing and what it costs, instead of leaving you with a greyed-out menu
  entry and no explanation.
- `path_manager` no longer prefers a bundled `ffmpeg/bin`; it looks at your
  stored path, the usual Windows install locations and your PATH.
- `check_ges.py` treats a missing ffmpeg as a hint, not as a failure.
- The ffmpeg render engine — `xfade_main()` with its pre-cutting, keyframe
  search, `copy_cut`, `crossfade_2`, concat, overlay encode and the
  VAAPI/NVENC parameters — was dead since the encode mode moved to GES. It is
  deleted, about 1200 lines. What remains of `managers/encoder_manager.py` is
  the export dialog and the segment length check that copy mode needs.

**What this means for licensing:** 6.0 no longer distributes an FFmpeg
program, so no GPL source obligation arises from it. It does still distribute
the FFmpeg **libraries** inside the GStreamer wheels — an LGPL build, covered
by `gstreamer/COMPONENTS.txt` and the GStreamer source directions. The source
offer for the GPL build shipped with 5.01 and earlier stays up: that
obligation belongs to the builds already handed out.

**mpv / libmpv is gone — GStreamer is now the only engine**

Up to 5.01 there were two playback paths and mpv was the default. It could
not show the crossfades at your cuts, had no real 360° mode, and was never
involved in the export anyway. Keeping it meant shipping a second video
runtime and maintaining two code paths for every feature. It is now removed:

- `core/player_backend.py` (the backend interface, the mpv implementation and
  the factory) is deleted. `VideoEditorWidget` builds `GesPlayerBackend`
  directly.
- Gone from the menus: *Config → Video Backend* and *Config → libmpv*. The
  QSettings keys `player/backend`, `paths/mpv` and `paths/mpv_mac` are no
  longer read.
- `path_manager.py` keeps only the ffmpeg helpers; the libmpv search, the
  validity checks and the macOS `find_library` patch are gone.
- `python-mpv` is out of `requirements.txt`.
- `build_with_pyinstaller.py` no longer copies `mpv/` into the build, so
  neither the portable ZIP nor the Inno Setup installer contains libmpv
  any more (110 MB less). A new `check_mpv_frei()` runs right before
  packing and aborts the build if any `mpv` folder, `libmpv*`/`mpv-*`
  library or the `mpv.py` binding turns up in it - shipping libmpv again
  by accident would silently re-create a GPL source obligation whose
  license texts are no longer in the bundle. The `mpv/` folder itself
  stays in the working tree; the 5.x branches still build from it.

**GStreamer is therefore a startup requirement now.** If it cannot be loaded,
KVRouite says so with the exact reason and the install command for the
platform, and points at `check_ges.py` — instead of failing later somewhere
in the user interface. ffmpeg stays optional (Copy-Mode only).

### Added

**True 360° video**

360° footage is stored equirectangular — the whole sphere squeezed into a 2:1
rectangle. Up to 5.01 KVRouite only cropped that distorted picture and moved
the crop around (mpv `panscan` + `video-zoom`/`video-pan`): no projection, no
wrap-around across the 360° seam, no real zoom — and the view never reached
the export, which always rendered the full distorted 2:1 image.

KVRouite now does the real thing with an OpenGL fragment shader
(`core/view360.py`), attached to each clip as a `GESEffect`:

- Look around by dragging in the picture, zoom with the mouse wheel, or use
  `Ctrl` + arrow keys / `Ctrl +` / `Ctrl -`, `Ctrl 0` to reset. Dragging is
  scaled by the current field of view, so it feels the same at any zoom.
- Straight lines stay straight, and panning across the seam is seamless.
- One viewing direction per video, stored in the project file (`view360`).
  *View → Apply 360° view to all videos* copies it to every clip, which is
  what you want for material from one camera.
- **The view is rendered.** Preview and export build the same timeline, so
  the export produces a normal 16:9 video showing exactly what the preview
  showed. Crossfades work: both halves are projected and then mixed.
- Measured: the shader costs nothing noticeable in the preview (30.0 fps with
  and without it on 1920x960 material), and it changes no timing — the same
  project rendered with and without 360° gives the identical frame count and
  duration.
- If the GL elements are missing (`gstreamer1.0-gl` on Linux, or no GL context
  over remote desktop), 360° simply stays off and says why; `check_ges.py`
  reports it.

**GStreamer / GES licensing and credits**

The GES backend brings a third-party runtime with it, and on Windows KVRouite
distributes that runtime. It is therefore documented like ffmpeg:

- New folder `gstreamer/` with `NOTICE.txt` (notice, patent notice, LGPL
  section 6 relinking note), `CORRESPONDING-SOURCE.txt`, `COMPONENTS.txt`
  (every shipped package with the license expression the package itself
  declares) and the full texts `COPYING.LGPL-2.1`, `COPYING.GPL-2`,
  `COPYING.GPL-3`. The wheels ship no license text of their own, so these had
  to be supplied.
- Unlike ffmpeg, no GStreamer sources are copied to kvrouite.com. These
  binaries are the GStreamer Project's own wheels, passed on unchanged, so the
  Corresponding Source is that project's 1.28.6 release tarballs - which GPLv3
  section 6(d) allows us to point at instead of rehosting, as long as clear
  directions travel with the binaries. `CORRESPONDING-SOURCE.txt` is those
  directions and explains the difference.
- `build_with_pyinstaller.py` copies `gstreamer/` to `_internal/gstreamer` and
  now reports whether the GStreamer runtime actually ended up in the build -
  if it did, the license texts are mandatory; if it did not, the build will not
  even start and is unusable.
- GStreamer, GES and PyGObject are named in the startup disclaimer, in
  `installer/AGREEMENT.txt`, in the README and on the website, with the split
  between the LGPL-2.1+ core and the GPL-2.0+ x264/x265 encoder plugins, and
  with the note that Linux redistributes nothing. Since mpv is no longer part
  of the distribution, it was taken out of all of those lists again, and out of
  the `_internal/...` folder lists they point at. The source offer for the
  libmpv shipped with 5.01 and earlier stays up at kvrouite.com - that
  obligation does not end when the next version drops the library.
- The patent notice now also names x264, AAC, MP3, AC-3 and DTS, not only x265.

### Fixed

**mpv was documented under the wrong license**

The README listed mpv as LGPLv2.1+. mpv is LGPL only when built without any
GPL-only files; the `libmpv-2.dll` that used to be shipped links libx264 and
libx265 and is a GPL build. It was corrected to GPL-2.0-or-later - which is
what the NOTICE always said - before mpv was dropped from the distribution
altogether. `mpv/NOTICE.txt` still carries the correct statement, for the
5.x branches that keep building from that folder.

**FFmpeg was listed under two different licenses**

The About dialog said GPL-2.0-or-later while `ffmpeg/NOTICE.txt`, the README,
`installer/AGREEMENT.txt` and the startup disclaimer all said
GPL-3.0-or-later. The About dialog now agrees with the other four.

**Notice files were copies of each other**

`ffmpeg/NOTICE.txt.txt` and `mpv/NOTICE.txt.txt` were byte-identical and each
described both libraries. They are now one file per component, named
`NOTICE.txt`, each describing only what is in its folder.

**License texts were missing from the repository**

`.gitignore` still had exceptions for `ffmpeg/VGSync_ffmpeg.txt` and
`mpv/VGSync_mpv.txt` - names from before the rename. The guidance files the
README points to, and the notice and license texts, were therefore not in the
repository at all. The exceptions now match the actual file names and also
cover `NOTICE.txt`, `LICENSE`, `LICENSE.GPL` and `Copyright`.

---

## 5.01 – unreleased

### Added

**Step along the cut edges**

The stepper button next to the forward/back arrows has a fifth setting: `c`.
It walks the video from cut edge to cut edge, frame by frame. Every cut gives
two stops - the last frame before it and the first frame after it - so you can
look at both sides of a joint and judge how the cut will play before rendering
anything. The first and the last frame of the finished video are stops as well.

`c` works in Encode Mode. There a keyframe is forced on every cut, so the two
frames you see are the ones that will end up next to each other. Copy Mode cuts
at the nearest keyframe instead, so the marked edges would not be what you get -
pressing the arrows there explains that and nothing moves. Use step mode `k` in
Copy Mode to see where the cut will really land.

The multiplier has no effect in `c`; it always goes one edge at a time.

**Hard cut instead of a crossfade**

In Encode Mode every cut is bridged with a crossfade. A single cut can now be
switched to a hard cut: right-click the black cut block in the timeline and
confirm the question. A hard cut is drawn with orange edges, so you can see at a
glance which cuts will blend and which will jump.

The cut position and the total length of the video do not change – only the
transition does: instead of blending the material before and after the cut, the
video jumps directly. The setting is stored in the project file and can be
reverted with Undo (Ctrl+Z).

While rendering, the encoder window now lists every cut and how it will be
produced:

```
[INFO] Cut 0.00s - 3.00s: trimmed away (video start)
[INFO] Cut 12.00s - 18.00s: hard cut (no crossfade)
[INFO] Cut 27.00s - 30.00s: crossfade 2.0s
```

Copy Mode has no crossfades at all, so there is nothing to switch there. The
first and the last cut cannot be switched either – they are trimmed away before
encoding and never had a crossfade.

**Lock Window Width (Config menu)**

Buttons appear and disappear while you work – when you switch to Edit mode, for
example. The window used to widen itself and the layout jumped. With this option
on, the window is measured once in its widest possible state and that width is
kept as the minimum. Nothing jumps any more. The window can still be enlarged by
hand, it just cannot be made narrower than the toolbars need.

On a small screen the reserved width can be wider than the screen itself – leave
the option off there.

**Reset Window Layout (Config menu)**

KVRouite now remembers the window size, the window position and the position of
the splitter – the divider between the left half (video and map) and the right
half (chart and GPX list) – when you close it, and restores them at the next
start. So the window only has to be arranged once.

This new menu entry forgets all of that and returns to the delivery state:
default size (16:9, 90 % of the screen), centred, splitter exactly 50/50.

**Tooltips in the info line**

Every value in the line under the GPX buttons now explains itself when the mouse
hovers over it.

### Changed

**Shorter labels in the info line**

`Video:` is now `V:`. `Length(GPX)` and `Duration(GPX)` were merged into a single
`GPX: 8.94km/00:04:25.565`. `Elevation Gain:` is now `Ele:`, `ZeroSpeed:` is now
`Zero:`, `TimeGaps:` is now `Gaps:`. The explanations moved into the tooltips.

This frees about 350 pixels in the GPX bar, and those pixels are what makes an
even 50/50 split possible on a smaller screen.

**KVRouite needs less screen width**

The smallest usable window width went down from 1295 to 1050 pixels. The 50/50
split now holds down to a window width of about 1200 pixels instead of 1700.
Checked against the startup size on screens from 1280x800 upwards: the window
fits everywhere and starts balanced.

**The Kinomap logo makes room**

When the GPX bar gets narrow, the logo hides itself instead of pushing the whole
window wider.

### Fixed

**The stepper now counts in the finished video**

The stepper measured its steps in the raw footage. A cut does not exist in the
finished video, but the step ran straight into it: `+1s` in front of a cut
landed inside the deleted range, and a "freeze" then parked the player at the
cut instead of stepping. On every cut longer than the step size you got stuck at
the edge and never moved on – with a cut of several minutes, `s` and `m` could
not get past it at all.

Steps are now measured in the finished video. Measured on a 29.97 fps project
with a cut from 1639.404 s to 1744.409 s, standing on the last frame before it:
`+1s` now lands at 1745.376 s, which is exactly one second later in the finished
video. It used to stop dead at the cut.

What changed per mode:

- `s` and `m` step their distance in the finished video and fly over cuts as if
  they were not there.
- `f` moves one frame in the finished video, so a single press takes you from the
  last frame before a cut to the first frame after it – it needed two before.
- `k` skips keyframes that fall inside a cut, because those do not exist in the
  result either.
- The freeze is gone. Looking at a cut edge is what the new `c` mode is for, and
  `c` and `f` now stop on exactly the same two frames.

The freeze also parked the player one millisecond before the cut, which is less
than one frame – you ended up on the first deleted frame, and the 200 ms preview
timer then threw you to the far end of the cut. That is what made it look as if
`s`, `m` and `k` could never reach a cut at all.

**The stepper assumed 25 fps for every video**

The frame rate was read from an mpv property that does not exist, so the lookup
silently fell back to 25 fps – on every file, at every frame rate. It now reads
`container-fps`, with `estimated-vf-fps` as a fallback.

This used to be almost harmless, because the value only fed a prediction that was
thrown away again. Now it decides where a frame boundary is, so it has to be
right: with 25 fps assumed, a step over a cut in 29.97 fps material would land on
the wrong frame. Checked against 24, 25, 29.97, 30, 50 and 60 fps material –
stepping over a cut lands on exactly the right frame in both directions at every
one of them.

**Cuts in Encode Mode are now frame-exact**

Every cut used to lose up to five frames: the cut was moved to the nearest
keyframe of the merged file instead of landing where it was marked. With many
cuts in one project the error added up. A keyframe is now forced at every cut
edge while merging, so the cut lands exactly on the mark.

Measured on a test project with a cut from 10.10 s to 20.10 s in a 30 s video:
the result is now 20.000 s instead of 19.833 s – a deviation of 0.000 s instead
of 0.167 s per cut.

This concerns Encode Mode only. Copy Mode cuts at keyframes by design, that has
not changed.

**GPX Summary showed rounded values**

The distance and the elevation gain shown in the GPX Summary were read back out
of the text in the info line instead of using the calculated numbers. The
elevation gain was therefore rounded to whole metres, and any change to the
labels would have made the distance silently drop to 0.00 km. Both values now
come straight from the calculation, and the elevation gain is shown with one
decimal.
