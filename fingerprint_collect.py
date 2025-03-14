
# fingerprint_collect.py

import platform
import subprocess
import re
import uuid
import hashlib
import win32com.client  # pywin32

def get_fingerprint_windows():
    hostname = platform.node()
    cpu_id = "CPU_UNKNOWN"
    board_sn = "BOARD_UNKNOWN"

    try:
        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        wmi_svc = locator.ConnectServer(".", "root\\cimv2")

        cpus = wmi_svc.ExecQuery("SELECT ProcessorId FROM Win32_Processor")
        for cpu in cpus:
            cpu_id = str(cpu.ProcessorId).strip()
            break

        boards = wmi_svc.ExecQuery("SELECT SerialNumber FROM Win32_BaseBoard")
        for bd in boards:
            board_sn = str(bd.SerialNumber).strip()
            break

    except Exception as e:
        print("[WARN] Could not read CPU/Board via pywin32 WMI:", e)

    raw_str = f"{hostname}-{cpu_id}-{board_sn}"
    h = hashlib.sha256(raw_str.encode("utf-8")).hexdigest().upper()
    return h[:16]

def get_fingerprint_linux():
    hostname = platform.node()
    vendor = "UNKNOWN_VENDOR"
    serial = "UNKNOWN_SERIAL"
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("vendor_id"):
                    vendor = line.split(":")[1].strip()
                elif line.startswith("Serial"):
                    serial = line.split(":")[1].strip()
    except:
        pass

    mac_int = uuid.getnode()
    mac_hex = f"{mac_int:012X}"
    raw_str = f"{hostname}-{vendor}-{serial}-{mac_hex}"
    h = hashlib.sha256(raw_str.encode("utf-8")).hexdigest().upper()
    return h[:16]

def get_fingerprint_universal():
    os_name = platform.system().lower()
    if os_name.startswith("win"):
        return get_fingerprint_windows()
    elif os_name.startswith("linux"):
        return get_fingerprint_linux()
    else:
        # fallback => Hostname + MAC
        hostname = platform.node()
        mac_int = uuid.getnode()
        mac_hex = f"{mac_int:012X}"
        raw_str = f"{hostname}-{mac_hex}"
        h = hashlib.sha256(raw_str.encode("utf-8")).hexdigest().upper()
        return h[:16]
