# core/hardware_detect.py
import subprocess

_cached_encoders = None  # Global Cache
_cached_already_printed_debug = False

def detect_available_hw_encoders(ffmpeg_path="ffmpeg"):
    """
    Ruft ffmpeg -encoders auf, um GPU-Encoder herauszufinden.
    Gibt ein set(...) zurück, z.B. {"CPU","nvidia_h264","nvidia_hevc","amd_h264","amd_hevc",...}
    
    "CPU" steht hier für den reinen Software-Encode (vormals "none").
    """
    import subprocess
    global _cached_encoders
    global _cached_already_printed_debug

    if _cached_encoders is not None:
        return _cached_encoders

    encoders_found = set()
    encoders_found.add("CPU")  # CPU = reine Software

    try:
        cmd = [ffmpeg_path, "-hide_banner", "-encoders"]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, encoding="utf-8")
    except Exception as e:
        print("[WARN] detect_available_hw_encoders failed:", e)
        print("[DEBUG] => No GPU encoders => returning {'CPU'}")
        _cached_encoders = {"CPU"}
        return _cached_encoders

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

    print("[DEBUG] => GPU encoders found:", encoders_found)
    _cached_encoders = encoders_found
    return _cached_encoders
