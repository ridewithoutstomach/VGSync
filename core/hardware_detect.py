# core/hardware_detect.py
import subprocess

_cached_encoders = None  # Global Cache
_cached_already_printed_debug = False

def detect_available_hw_encoders(ffmpeg_path="ffmpeg"):
    """
    Ruft ffmpeg -encoders auf, um GPU-Encoder herauszufinden.
    Gibt ein set(...) zurück, z.B. {"none","nvidia_h264","nvidia_hevc","amd_h264","amd_hevc",...}
    
    - Nur beim ersten Aufruf führen wir subprocess aus und drucken die Debug-Zeilen.
    - Bei folgenden Aufrufen geben wir das gecachte Set zurück, ohne Debugspam.
    """

    global _cached_encoders
    global _cached_already_printed_debug

    if _cached_encoders is not None:
        # => schon mal ermittelt => direkt zurück
        return _cached_encoders

    encoders_found = set()

    try:
        cmd = [ffmpeg_path, "-hide_banner", "-encoders"]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, encoding="utf-8")
    except Exception as e:
        print("[WARN] detect_available_hw_encoders failed:", e)
        print("[DEBUG] => No GPU encoders => returning {'none'}")
        _cached_encoders = {"none"}
        return _cached_encoders

    # Nur beim ersten Mal debug-ausgabe
    """
    if not _cached_already_printed_debug:
        lines = output.splitlines()
        print("[DEBUG] ffmpeg -encoders output (shortened):")
        for ln in lines[:20]:
            print("   ", ln)
        if len(lines) > 20:
            print(f"   ... ({len(lines)} total lines)")
        _cached_already_printed_debug = True
    """
    # Encoder-Strings => Mapping
    if "h264_nvenc" in output:
        encoders_found.add("nvidia_h264")
    if "hevc_nvenc" in output:
        encoders_found.add("nvidia_hevc")

    if "h264_amf" in output:
        encoders_found.add("amd_h264")
    if "hevc_amf" in output:
        encoders_found.add("amd_hevc")

    if "h264_qsv" in output:
        encoders_found.add("intel_h264")
    if "hevc_qsv" in output:
        encoders_found.add("intel_hevc")

    if not encoders_found:
        encoders_found = {"none"}

    print("[DEBUG] => GPU encoders found:", encoders_found)

    _cached_encoders = encoders_found
    return _cached_encoders
