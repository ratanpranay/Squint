"""Screen recording: a region as an MP4 video, or as a GIF of at most six
seconds. Enter stops, Escape cancels, from whatever window is in front."""
import os
import subprocess
import time

from . import common
from .capture import Outline, exclude_from_capture, pick_region

GIF_SECONDS = 6
GIF_FPS = 10
GIF_MAX_WIDTH = 800


def video(ctrl, **_):
    if not common.IS_WINDOWS:
        common.tell(ctrl, "Video recording is Windows-only for now.")
        return
    image, box = pick_region(ctrl)
    if image is None:
        return
    common.with_tool(ctrl, "ffmpeg", "Getting the video tools (once)",
                     lambda ffmpeg: _start_video(ctrl, ffmpeg, box))


def _start_video(ctrl, ffmpeg, box):
    left, top, w, h = box
    w -= w % 2                               # H.264 wants even sizes
    h -= h % 2
    path = common.unique(os.path.join(common.videos_dir(),
                                      "Recording %s.mp4" % common.stamp()))
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "gdigrab", "-framerate", "30",
            "-offset_x", str(left), "-offset_y", str(top),
            "-video_size", "%dx%d" % (w, h), "-draw_mouse", "1",
            "-i", "desktop",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", path]
    proc = subprocess.Popen(args, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                            creationflags=common.NO_WINDOW)
    outline = Outline(ctrl.root, box)

    def stop():
        outline.close()

        def work():
            try:
                proc.stdin.write(b"q")
                proc.stdin.flush()
            except Exception:
                pass
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                err = proc.stderr.read().decode("utf-8", "replace")
                raise RuntimeError(err.strip()[-300:] or "nothing recorded")
            return path

        common.in_background(
            ctrl, work, lambda p: common.tell(ctrl, "Recording saved.", p),
            "Recording")

    def cancel():
        outline.close()
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass
        try:
            os.remove(path)
        except OSError:
            pass

    bar = common.StopBar(ctrl, "Recording video", stop, cancel, avoid=box)
    exclude_from_capture(bar.win)
    ctrl.radial_recording = bar


def gif(ctrl, **_):
    image, box = pick_region(ctrl)
    if image is None:
        return
    import mss
    from PIL import Image
    grabber = mss.mss()
    left, top, w, h = box
    area = {"left": left, "top": top, "width": w, "height": h}
    frames = []
    state = {"running": True, "next": time.time()}
    outline = Outline(ctrl.root, box)

    def grab():
        if not state["running"]:
            return
        try:
            raw = grabber.grab(area)
            frames.append(Image.frombytes("RGB", raw.size, raw.bgra, "raw",
                                          "BGRX"))
        except Exception as exc:           # noqa: BLE001
            common.log("gif grab: %r" % exc)
        state["next"] += 1.0 / GIF_FPS
        delay = max(1, int((state["next"] - time.time()) * 1000))
        ctrl.root.after(delay, grab)

    def stop():
        state["running"] = False
        outline.close()
        if not frames:
            return
        common.in_background(ctrl, lambda: save_gif(frames), lambda p:
                             common.tell(ctrl, "GIF saved.", p), "GIF")

    def cancel():
        state["running"] = False
        outline.close()

    bar = common.StopBar(ctrl, "Recording GIF (stops at %d s)" % GIF_SECONDS,
                         stop, cancel, limit=GIF_SECONDS, avoid=box)
    exclude_from_capture(bar.win)
    ctrl.radial_recording = bar
    ctrl.root.after(0, grab)


def save_gif(frames, folder=None):
    from PIL import Image
    first = frames[0]
    if first.width > GIF_MAX_WIDTH:
        ratio = GIF_MAX_WIDTH / float(first.width)
        size = (GIF_MAX_WIDTH, max(1, int(first.height * ratio)))
        frames = [f.resize(size, Image.LANCZOS) for f in frames]
    # One palette for the whole clip keeps colours from flickering.
    palette = frames[0].quantize(colors=255, method=Image.MEDIANCUT)
    quantised = [f.quantize(palette=palette, dither=Image.NONE)
                 for f in frames]
    path = common.unique(os.path.join(folder or common.videos_dir(),
                                      "GIF %s.gif" % common.stamp()))
    quantised[0].save(path, save_all=True, append_images=quantised[1:],
                      duration=int(1000 / GIF_FPS), loop=0, optimize=True)
    return path
