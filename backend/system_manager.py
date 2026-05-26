"""Windows system management: processes, resources, files, hardware."""

import os
import sys
import subprocess
import json
import platform
from datetime import datetime

import psutil


def get_system_snapshot() -> dict:
    """Quick snapshot for context injection into AI."""
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu": round(cpu, 1),
        "ram": round(ram.percent, 1),
        "ram_used_gb": round(ram.used / 1e9, 2),
        "ram_total_gb": round(ram.total / 1e9, 2),
        "disk_used_gb": round(disk.used / 1e9, 2),
        "disk_total_gb": round(disk.total / 1e9, 2),
        "disk_percent": round(disk.percent, 1),
        "processes": len(psutil.pids()),
    }


def get_full_system_info() -> dict:
    """Detailed system hardware and OS information."""
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname": platform.node(),
        "python_version": platform.python_version(),
        "boot_time": datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S"),
    }

    # CPU
    info["cpu"] = {
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "usage_percent": psutil.cpu_percent(interval=0.5),
        "freq_mhz": round(psutil.cpu_freq().current) if psutil.cpu_freq() else "N/A",
    }

    # RAM
    ram = psutil.virtual_memory()
    info["ram"] = {
        "total_gb": round(ram.total / 1e9, 2),
        "used_gb": round(ram.used / 1e9, 2),
        "available_gb": round(ram.available / 1e9, 2),
        "percent": ram.percent,
    }

    # Disk
    disks = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total_gb": round(usage.total / 1e9, 2),
                "used_gb": round(usage.used / 1e9, 2),
                "free_gb": round(usage.free / 1e9, 2),
                "percent": usage.percent,
            })
        except Exception:
            pass
    info["disks"] = disks

    # Network
    net = psutil.net_if_addrs()
    interfaces = {}
    for iface, addrs in net.items():
        interfaces[iface] = [
            {"family": str(addr.family), "address": addr.address}
            for addr in addrs
        ]
    info["network_interfaces"] = interfaces

    # Battery (laptops)
    battery = psutil.sensors_battery()
    if battery:
        info["battery"] = {
            "percent": round(battery.percent, 1),
            "plugged_in": battery.power_plugged,
            "time_left_min": round(battery.secsleft / 60) if battery.secsleft > 0 else "Charging",
        }

    return info


def list_processes(sort_by: str = "cpu", limit: int = 20) -> list:
    """List running processes sorted by CPU or memory."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            info = p.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"] or "Unknown",
                "cpu": round(info["cpu_percent"] or 0, 1),
                "mem": round(info["memory_percent"] or 0, 2),
                "status": info["status"],
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if sort_by == "memory":
        procs.sort(key=lambda x: x["mem"], reverse=True)
    else:
        procs.sort(key=lambda x: x["cpu"], reverse=True)

    return procs[:limit]


def kill_process(identifier) -> dict:
    """Kill a process by PID or name."""
    killed = []
    errors = []

    try:
        pid = int(identifier)
        try:
            p = psutil.Process(pid)
            name = p.name()
            p.terminate()
            killed.append(f"{name} (PID {pid})")
        except psutil.NoSuchProcess:
            errors.append(f"PID {pid} not found")
        except psutil.AccessDenied:
            errors.append(f"Access denied for PID {pid}")
    except ValueError:
        # It's a name
        name = str(identifier)
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if p.info["name"] and name.lower() in p.info["name"].lower():
                    p.terminate()
                    killed.append(f"{p.info['name']} (PID {p.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    return {"killed": killed, "errors": errors}


def search_files(query: str, search_path: str = None, limit: int = 20) -> list:
    """Search for files by name pattern."""
    if not search_path:
        search_path = os.path.expanduser("~") if sys.platform != "win32" else "C:\\"

    results = []
    query_lower = query.lower()

    try:
        for root, dirs, files in os.walk(search_path):
            # Skip hidden/system directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {
                "Windows", "System32", "$Recycle.Bin", "AppData\\Local\\Temp",
                "__pycache__", "node_modules", ".git"
            }]

            for fname in files:
                if query_lower in fname.lower():
                    full_path = os.path.join(root, fname)
                    try:
                        stat = os.stat(full_path)
                        results.append({
                            "name": fname,
                            "path": full_path,
                            "size_kb": round(stat.st_size / 1024, 1),
                            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        })
                    except Exception:
                        results.append({"name": fname, "path": full_path})

                    if len(results) >= limit:
                        return results
    except PermissionError:
        pass

    return results


def get_network_stats() -> dict:
    """Get current network I/O statistics."""
    stats = psutil.net_io_counters()
    connections = psutil.net_connections()
    established = sum(1 for c in connections if c.status == "ESTABLISHED")
    return {
        "bytes_sent_mb": round(stats.bytes_sent / 1e6, 2),
        "bytes_recv_mb": round(stats.bytes_recv / 1e6, 2),
        "packets_sent": stats.packets_sent,
        "packets_recv": stats.packets_recv,
        "established_connections": established,
        "total_connections": len(connections),
    }


def get_top_memory_processes(limit: int = 5) -> list:
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x.get("memory_percent") or 0, reverse=True)
    return procs[:limit]


def launch_application(app_name: str) -> dict:
    """Launch an application by name (Windows)."""
    app_map = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "paint": "mspaint.exe",
        "explorer": "explorer.exe",
        "task manager": "taskmgr.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "edge": "msedge.exe",
        "chrome": "chrome.exe",
        "firefox": "firefox.exe",
        "word": "winword.exe",
        "excel": "excel.exe",
        "control panel": "control.exe",
        "settings": "ms-settings:",
    }

    name_lower = app_name.lower().strip()
    exe = app_map.get(name_lower, app_name)

    try:
        if sys.platform == "win32":
            os.startfile(exe) if ":" in exe else subprocess.Popen([exe])
        else:
            subprocess.Popen(["xdg-open", exe])
        return {"success": True, "launched": exe}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_volume(level: int) -> dict:
    """Set system volume 0-100 (Windows only)."""
    if sys.platform != "win32":
        return {"success": False, "error": "Windows only"}
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        import math

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        scalar = max(0.0, min(1.0, level / 100.0))
        volume.SetMasterVolumeLevelScalar(scalar, None)
        return {"success": True, "volume": level}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_startup_programs() -> list:
    """List startup programs from Windows registry."""
    if sys.platform != "win32":
        return []
    try:
        import winreg
        results = []
        keys = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        ]
        for hive, path in keys:
            try:
                key = winreg.OpenKey(hive, path)
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        results.append({"name": name, "path": value})
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except Exception:
                pass
        return results
    except Exception:
        return []
