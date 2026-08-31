# Changelog

All notable changes to KVRouite are listed here, newest version first.
The GitHub release page is shorter and written for users; this file is the
detailed record.

Versions up to and including 5.0 are documented in the GitHub releases only.

---

## 6.01 – 2026-08-31

Nothing was added and nothing moved. This release is about the application
getting out of the way, plus three defects that shipped with 6.0.

### Fixed

**Cut Begin cut too far into the video from the second file onwards**

`get_current_position_s()` returns the GLOBAL time across all files, but the
caller in `on_set_begin_clicked()` treated it as a time within the current clip
and added the offset of the preceding files a second time. From the second video
on, the cut was placed too late by the summed length of everything before it.
With two files and the marker in the second one, the computed cut end could
exceed the total length and the whole timeline went black.

`EndManager.go_to_end()` and the sync path were never affected - they use the
value directly. The same block sits commented out in `on_sync_clicked()`, so it
had been noticed there once before and fixed only in that one place.

**Cut End left the last frame of the raw video behind**

Cut marks come from `real_total_duration`, which is read from the mdhd box of
the file. The preview computes its keep ranges against `asset.get_duration()`
from GES. The two disagree by a fraction of a millisecond, so an end cut ended
just short of the raw end - and `_compute_keeps()` appended what was left as a
keep range of its own. That sliver was the very last frame of the raw video, and
because it was the final piece of the preview, *Go to End* and playback landed
on it instead of on the frame before the cut.

Keep ranges shorter than 10 ms are no longer created. At any frame rate up to
100 fps a range that short cannot hold a single complete frame, so it can only
ever be a rounding remainder between the two sources.

**An end cut could leave the map unusable**

See the map entry below - it is the same cause.

### Changed

**The map**

`ol.interaction.Modify`, the machinery behind the map's `Move` button, was
created at startup with `source:` and therefore listened to the point source for
the whole session, whether or not `Move` was ever pressed. Every change and
every removal of a point is reported to it, and its bookkeeping walks its entire
internal index for each one - `removeFeatureSegmentData_()` in `ol.js` builds a
full copy of the index and scans it linearly.

With a five-hour track at 1 Hz - about 17,000 points - that meant:

- reloading the map after a cut, a deletion or a GoPro extraction: **14 to 17
  seconds**, measured inside the map itself
- an end cut, which recolours every point after the cut through
  `mark_range_in_red()`: 16,000 of those scans, one after another. The map
  stopped responding.

It is now created when `Move` is switched on, over its own feature list rather
than over the source, and discarded when `Move` is switched off. In normal use
that index does not exist at all.

Two further changes to the map, both in `map_page.html`:

- Point styles are shared instead of built per point. OpenLayers caches the
  rendered circle image on the style OBJECT, so 17,000 individual styles meant
  the cache never applied and 17,000 circles were drawn separately - at load and
  again on every pan and zoom. There are only a handful of distinct styles.
- Features are inserted with one `addFeatures()` call instead of `addFeature()`
  per point.

**The elevation and speed chart no longer stutters the video**

`ChartWidget.paintEvent()` recomputed everything on every repaint - collecting
elevation and speed for all points, finding minima and maxima, building two
point lists, then drawing one line per point. At 17,000 points that is about
35,000 drawing calls, five times a second, in the same thread that paints the
video frames. Measured offscreen: **25 ms at 17,329 points, 42 ms at 28,800**.
A video frame lasts 33 ms at 30 fps.

While the video plays, none of the curves change - only the marker moves. The
curves are now drawn once into an image and reused; each tick copies that image
and draws the marker on top. Measured: **0.06 ms**. The image is rebuilt when
the data, size, zoom, offset, thresholds, sync range or GPX-video shift change.

**One timing loop instead of two**

The time display had its own 200 ms timer in `VideoEditorWidget` that queried
the player position a second time and ran against the marker timer. Marker and
time display could therefore show two different points in the same video. The
display is now refreshed from the marker tick with the position already
determined there.

**The stepper goes straight to its target**

Three things made stepping unsteady, all of them left over from the playlist
model of the previous video engine:

- `_position_ns()` returned `0` when the position query failed - which happens
  regularly during a seek or a state change. `0` is also a valid position,
  namely the beginning, so the caller could not tell the two apart, and that `0`
  reached the timeline marker. It now returns `None`, and callers fall back to
  the last known position.
- `seek_global()` split the target into clip index plus local second, compared
  that with the player's live index and, when they differed, first seeked to the
  START of the clip - position 0.000 s for the first clip - and only 100 ms
  later to the actual target. That was the visible jump to the beginning when
  stepping across a clip boundary. GES has one continuous timeline; the seek now
  goes straight there. `show_first_frame_at_index()` and *Go to Start* did the
  same thing twice as well, both times to the identical position.
- `get_current_global_time()` combined two separate position queries - the
  offset from one, the local time from the other. If they drifted apart, the
  result jumped by a whole clip length. It is one query now.

**A 200 ms timer from the mpv era is gone**

`VideoCutManager` checked five times a second whether the player had wandered
into a cut range and pushed it out. GES removes cut ranges from the timeline
physically, so a cut position cannot be reached at all - the timer could only
fire on a distorted position reading, and then it moved the picture on its own.
Its repair mechanisms went with it, including a monkey patch that disabled the
timeline marker for 50 ms at a time. About 150 lines.

**Seeks no longer block the interface**

Every seek waited for its own completion with a one second cap, in the GUI
thread. It now records that a seek is running and clears that on `ASYNC_DONE`
from the bus; while it runs, the position query answers with the seek target
instead of a measurement that would still return the old position. A seek that
would overtake a running one still waits - GStreamer rejects it otherwise and
the picture stays where it was.

*Go to End* and the end-cut handler fired the same seek three times, at 10, 100
and 250 ms. Once is enough.

**Dragging the timeline marker**

Every mouse movement triggered its own seek. At most one per 60 ms now; the last
position is always reached.

**Single-frame stepping above 30 fps**

The preview is capped at 30 fps. `step_frame()` computed its step from the
SOURCE frame rate, so with 50 or 60 fps material a step was less than one
visible frame and only every second press changed the picture. The stepper now
works in the frame rate of the preview - as does the edge arithmetic in
`StepManager`, so both use the same duration. At 25, 29.97 or 30 fps nothing
changes.

**Finding the nearest GPX point**

`get_closest_index_for_time()` scanned all timestamps on every call, twice per
200 ms tick - 0.74 ms at 17,329 points. The timestamps are ascending, so a
binary search does the same in 0.0004 ms. Whether they really are ascending is
checked while the list is built; points without a timestamp get 0.0, and if that
breaks the order the linear scan is used as before. 24,020 cases were checked
against the old search with no difference in result.

---

## 6.0 – 2026-08-30

### Changed

**The video engine was rebuilt on GStreamer Editing Services**

Up to 5.01 there were two playback paths and a separate render engine. Preview
and export now build the same GES timeline, so the preview shows what the
render will produce - cut ranges are gone from the picture and the crossfades
sit at the cuts.

- Crossfades are pre-rendered in the background while you keep working
  (`core/fade_cache.py`). Finished ones are reused; a cut without a rendered
  fade shows as a hard cut until it arrives.
- `core/player_backend.py` - the backend interface, the second implementation
  and the factory - is deleted. `VideoEditorWidget` builds `GesPlayerBackend`
  directly.
- Gone from the menus: *Config -> Video Backend* and *Config -> libmpv*.
- `path_manager.py` keeps only the ffmpeg helpers.
- The old render engine - `xfade_main()` with its pre-cutting, keyframe search,
  `copy_cut`, `crossfade_2`, concat, overlay encode and the VAAPI/NVENC
  parameters - is deleted, about 1200 lines. What remains of
  `managers/encoder_manager.py` is the export dialog and the segment length
  check that copy mode needs.
- **GStreamer is a startup requirement.** If it cannot be loaded, KVRouite says
  so with the exact reason and the install command for the platform, and points
  at `check_ges.py`, instead of failing later somewhere in the user interface.

**Rendering is much faster**

The old export ran in several passes over the material: pre-cutting the
segments, searching keyframes, rendering each crossfade on its own, joining
everything back together and, if overlays were used, encoding the result a
further time - with intermediate files at every step. GES builds one timeline
and renders it in a single pass.

Measured on the reference project - two GoPro files, 3840x2160 H.265 at
29.97 fps, 11.9 GB each, 70 minutes of raw material cut down to 4.4 minutes
with five cuts, three of them with a crossfade, and two overlays. Both renders
used NVENC hardware encoding on the same machine: about 15 minutes before,
about two minutes now.

That is a rough indication of the new engine, not a benchmark - the time
depends on the machine, the material and the encoder settings. The gain grows
with the number of cuts, because every cut used to add work of its own.

The Windows build is also about 100 MB smaller, since it no longer carries a
second video runtime or the render engine it used to ship.

**Copy mode uses the ffmpeg on your system**

Rendering runs through GES, so ffmpeg is only still used by copy mode, which
cuts on keyframes with `-c copy`.

- Copy mode is enabled only when **both** `ffmpeg` and `ffprobe` are in your
  PATH. It used to check only `ffmpeg`, so having just one of them led into a
  mode that failed at export.
- KVRouite says once at startup what is missing and what it costs, instead of
  leaving a greyed-out menu entry with no explanation.
- `path_manager` looks at your stored path, the usual Windows install locations
  and your PATH.
- `check_ges.py` treats a missing ffmpeg as a hint, not as a failure.

### Added

**True 360° video**

360° footage is stored equirectangular - the whole sphere squeezed into a 2:1
rectangle. Up to 5.01 KVRouite only cropped that distorted picture and moved
the crop around: no projection, no wrap-around across the 360° seam, no real
zoom - and the view never reached the export, which always rendered the full
distorted 2:1 image.

KVRouite now does the real thing with an OpenGL fragment shader
(`core/view360.py`), attached to each clip as a `GESEffect`:

- Look around by dragging in the picture, zoom with the mouse wheel, or use
  `Ctrl` + arrow keys / `Ctrl +` / `Ctrl -`, `Ctrl 0` to reset. Dragging is
  scaled by the current field of view, so it feels the same at any zoom.
- Straight lines stay straight, and panning across the seam is seamless.
- One viewing direction per video, stored in the project file (`view360`).
  *View -> Apply 360° view to all videos* copies it to every clip, which is
  what you want for material from one camera.
- **The view is rendered.** Preview and export build the same timeline, so the
  export produces a normal 16:9 video showing exactly what the preview showed.
  Crossfades work: both halves are projected and then mixed.
- Measured: the shader costs nothing noticeable in the preview (30.0 fps with
  and without it on 1920x960 material), and it changes no timing - the same
  project rendered with and without 360° gives the identical frame count and
  duration.
- If the GL elements are missing (`gstreamer1.0-gl` on Linux, or no GL context
  over remote desktop), 360° simply stays off and says why; `check_ges.py`
  reports it.

**Overlays**

Images can be placed on the timeline, positioned in the picture and are
rendered into the export.

### Removed

**Street view and the create mode**

The street view pane was only ever visible inside the create mode, and the
create mode existed to place GPX points next to it. Both are gone, together
with the Mapillary key entry. Building GPX points still works: *new points at
video time* and *directions* remain as their own menu entries.

### Fixed

**Loading a second project could stall the preview**

Loading a project while another one was open started the crossfade
pre-rendering in the middle of the load - still in the mode of the previous
project - and could leave the progress window waiting forever. Two causes, both
fixed: the preview is no longer rebuilt while a project is loading, and the
render loop can no longer stop without reporting a result.

**The keyframe index travelled between projects**

The index was written into the project file and only ever cleared by *New
Project*, so a project could carry the keyframes of videos that were no longer
loaded. It is no longer stored: when a project is loaded the index is read
directly from the video files, which takes milliseconds, and it is dropped when
the playlist changes. Project files are much smaller as a result.

---

## 5.01 – 2026-08-28

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

**Rendered videos could come out several seconds too short**

Before merging, every pre-trimmed part is measured to find out how much of it is
really playable, and that length is written into the concat list. The
measurement could return a value that was far too small. ffmpeg then trimmed the
part down to that length while merging, and the finished video was short by the
difference.

Measured on a project with two 60 s clips and one cut from 30 s to 90 s:

    part 1 reported  55.033 s   instead of  60.000 s
    part 2 reported  55.700 s   instead of  60.833 s
    merged file      115.933 s  instead of 120.833 s   (147 frames dropped)
    final video       55.933 s  instead of  60.833 s

The cut itself was placed correctly - the material after it simply started
almost five seconds too late.

The cause was the interval passed to ffprobe. `START%` without an explicit end
does not reliably mean "to the end of the file": depending on the file it
returned nothing at all, or only the very first frame of the interval. In the
second case the file was reported short by the width of the measuring window,
which is five seconds.

The interval now has an explicit end. On top of that the result is checked for
plausibility: this measurement exists to subtract a small overhang - at most one
GOP, measured 0.901 s - so anything more than 1.5 s below the container length is
discarded and the container value is used instead. That is the behaviour from
before this measurement existed: at worst a stutter at a joint, never a video
that is too short.

Measured after the change: five consecutive renders of the same project, all
exactly 60.833333 s, with the measurement returning correct values every time.
Before the change the same code returned a usable value in only one of three
runs. Forcing the faulty answers by hand - first frame only, two frames, no
answer at all - is now caught in every case, while a genuine correction of
0.9 s still goes through.

This affects 5.0 as well. The measurement arrived with the merge fix that first
shipped in 5.0; releases up to and including 4.34 do not contain it and are not
affected.

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
