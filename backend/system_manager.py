"""Windows system management — routes through PowerShell when running in WSL2."""

import os
import sys
import subprocess
import json
import platform
from datetime import datetime

import psutil

# ── WSL detection ──────────────────────────────────────────────────────────────

def _is_wsl() -> bool:
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False

IS_WSL = _is_wsl()


def _ps(cmd: str, timeout: int = 15) -> str:
    """Run a PowerShell command on the Windows host and return stdout."""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout.strip()


def run_powershell(command: str, timeout: int = 60) -> dict:
    """Execute a PowerShell command elevated (UAC prompt) on the Windows host.

    Strategy:
      1. Base64-encode the user command to sidestep all quoting issues.
      2. Write it to a temp .ps1 via a non-elevated PS bridge.
      3. Build an elevated runner script that executes the .ps1 and redirects
         all output (2>&1) into a temp output file, also base64-encoded.
      4. Launch that runner via Start-Process -Verb RunAs -Wait (shows UAC).
      5. Read back the output file, clean up, return.
    """
    import base64
    import time

    ts = int(time.time())

    # Encode the user command so it survives the here-string boundary
    encoded_cmd = base64.b64encode(command.encode("utf-16-le")).decode()

    # The bridge script runs unelevated; it:
    #   • decodes the command and writes it to a temp .ps1
    #   • builds the elevated runner command (also base64-encoded)
    #   • calls Start-Process -Verb RunAs -Wait (UAC dialog appears here)
    #   • reads and prints the captured output
    bridge = f"""
$ts         = '{ts}'
$scriptFile = "$env:TEMP\\sai_cmd_$ts.ps1"
$outFile    = "$env:TEMP\\sai_out_$ts.txt"

# Decode and save the user command
$bytes   = [Convert]::FromBase64String('{encoded_cmd}')
$decoded = [Text.Encoding]::Unicode.GetString($bytes)
Set-Content -Path $scriptFile -Value $decoded -Encoding UTF8

# Build the elevated runner: execute script, capture all output to file
$elevCmd = "& '$scriptFile' 2>&1 | Out-File -FilePath '$outFile' -Encoding UTF8"
$elevEnc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($elevCmd))

# UAC prompt fires here; -Wait blocks until the elevated process exits
Start-Process powershell.exe -Verb RunAs -Wait -WindowStyle Hidden `
    -ArgumentList '-NoProfile', '-NonInteractive', '-EncodedCommand', $elevEnc

Start-Sleep -Milliseconds 400
$result = Get-Content $outFile -Raw -ErrorAction SilentlyContinue
Remove-Item $scriptFile, $outFile -Force -ErrorAction SilentlyContinue

if ($result) {{ $result.Trim() }} else {{ '[No output - UAC may have been cancelled]' }}
"""

    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", bridge],
            capture_output=True, text=True, timeout=timeout + 30,
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        return {
            "stdout": stdout if stdout else (stderr or "[No output]"),
            "stderr": stderr,
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Timed out after {timeout}s", "exit_code": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1}


# ── System snapshot ────────────────────────────────────────────────────────────

def get_system_snapshot() -> dict:
    if IS_WSL:
        return _snapshot_wsl()
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


def _snapshot_wsl() -> dict:
    script = """
$cpu = (Get-WmiObject Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
$os  = Get-WmiObject Win32_OperatingSystem
$ram_pct  = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize * 100, 1)
$ram_used = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / 1MB, 2)
$ram_tot  = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
$d = Get-PSDrive C
$disk_used = [math]::Round($d.Used / 1GB, 2)
$disk_tot  = [math]::Round(($d.Used + $d.Free) / 1GB, 2)
$disk_pct  = [math]::Round($d.Used / ($d.Used + $d.Free) * 100, 1)
$procs = (Get-Process).Count
[PSCustomObject]@{cpu=$cpu;ram=$ram_pct;ram_used_gb=$ram_used;ram_total_gb=$ram_tot;disk_used_gb=$disk_used;disk_total_gb=$disk_tot;disk_percent=$disk_pct;processes=$procs} | ConvertTo-Json
"""
    try:
        data = json.loads(_ps(script))
        return {k: (round(float(v), 2) if isinstance(v, (int, float)) else v) for k, v in data.items()}
    except Exception:
        # Fallback to psutil (shows WSL stats at least)
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        return {"cpu": round(cpu, 1), "ram": round(ram.percent, 1), "processes": len(psutil.pids())}


# ── Full system info ───────────────────────────────────────────────────────────

def get_full_system_info() -> dict:
    if IS_WSL:
        return _full_info_wsl()
    # Native Windows / Linux
    info = {
        "os": platform.system(), "os_version": platform.version(),
        "hostname": platform.node(), "processor": platform.processor(),
    }
    info["cpu"] = {
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "usage_percent": psutil.cpu_percent(interval=0.5),
    }
    ram = psutil.virtual_memory()
    info["ram"] = {"total_gb": round(ram.total/1e9,2), "used_gb": round(ram.used/1e9,2), "percent": ram.percent}
    return info


def _full_info_wsl() -> dict:
    script = """
$cpu  = Get-WmiObject Win32_Processor | Select-Object -First 1
$os   = Get-WmiObject Win32_OperatingSystem
$disk = Get-PSDrive C
$ram_used = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory)/1MB, 2)
$ram_tot  = [math]::Round($os.TotalVisibleMemorySize/1MB, 2)
$bat  = Get-WmiObject Win32_Battery -ErrorAction SilentlyContinue
[PSCustomObject]@{
  os            = $os.Caption
  os_version    = $os.Version
  hostname      = $env:COMPUTERNAME
  cpu_name      = $cpu.Name
  cpu_cores     = $cpu.NumberOfCores
  cpu_threads   = $cpu.NumberOfLogicalProcessors
  cpu_load      = $cpu.LoadPercentage
  ram_total_gb  = $ram_tot
  ram_used_gb   = $ram_used
  ram_pct       = [math]::Round($ram_used/$ram_tot*100,1)
  disk_used_gb  = [math]::Round($disk.Used/1GB,2)
  disk_free_gb  = [math]::Round($disk.Free/1GB,2)
  disk_total_gb = [math]::Round(($disk.Used+$disk.Free)/1GB,2)
  battery_pct   = if($bat){$bat.EstimatedChargeRemaining}else{"N/A"}
  battery_plug  = if($bat){$bat.BatteryStatus -eq 2}else{"N/A"}
} | ConvertTo-Json
"""
    try:
        return json.loads(_ps(script))
    except Exception as e:
        return {"error": str(e)}


# ── Process list ───────────────────────────────────────────────────────────────

def list_processes(sort_by: str = "cpu", limit: int = 20) -> list:
    if IS_WSL:
        return _list_processes_wsl(sort_by, limit)
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            info = p.info
            procs.append({"pid": info["pid"], "name": info["name"] or "Unknown",
                          "cpu": round(info["cpu_percent"] or 0, 1),
                          "mem": round(info["memory_percent"] or 0, 2),
                          "status": info["status"]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x["mem" if sort_by == "memory" else "cpu"], reverse=True)
    return procs[:limit]


def _list_processes_wsl(sort_by: str, limit: int) -> list:
    # Two-snapshot delta: take CPU (seconds) before and after a 1s sleep.
    # delta / 1s / cores * 100 gives real-time %. Avoids Get-Counter locale issues
    # and WMI PerfFormattedData's broken first-call values.
    script = f"""
$snap1 = @{{}}
Get-Process -ErrorAction SilentlyContinue | ForEach-Object {{
    if ($null -ne $_.CPU) {{ $snap1[$_.Id] = [double]$_.CPU }}
}}

Start-Sleep -Milliseconds 1000

$cores = try {{ (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors }} catch {{ 1 }}
if (!$cores -or $cores -lt 1) {{ $cores = 1 }}

$result = Get-Process -ErrorAction SilentlyContinue | ForEach-Object {{
    $cpuPct = 0.0
    if ($snap1.ContainsKey($_.Id) -and $null -ne $_.CPU) {{
        $delta  = [math]::Max(0.0, [double]$_.CPU - $snap1[$_.Id])
        $cpuPct = [math]::Round($delta / 1.0 / $cores * 100, 1)
    }}
    [PSCustomObject]@{{
        pid  = $_.Id
        name = $_.Name
        cpu  = $cpuPct
        mem  = [math]::Round($_.WorkingSet / 1MB, 1)
    }}
}}

if ('{sort_by}' -eq 'memory') {{
    $sorted = $result | Sort-Object mem -Descending
}} else {{
    $sorted = $result | Sort-Object cpu -Descending
}}

$sorted | Select-Object -First {limit} pid, name, cpu, mem | ConvertTo-Json
"""
    try:
        raw = json.loads(_ps(script, timeout=25))
        if isinstance(raw, dict):
            raw = [raw]
        for p in raw:
            p.setdefault("status", "running")
        return raw
    except Exception:
        return []


# ── Kill process ───────────────────────────────────────────────────────────────

def kill_process(identifier) -> dict:
    if IS_WSL:
        return _kill_process_wsl(identifier)
    killed, errors = [], []
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
        name = str(identifier)
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if p.info["name"] and name.lower() in p.info["name"].lower():
                    p.terminate()
                    killed.append(f"{p.info['name']} (PID {p.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return {"killed": killed, "errors": errors}


def _kill_process_wsl(identifier) -> dict:
    try:
        pid = int(identifier)
        out = _ps(f"Stop-Process -Id {pid} -Force -ErrorAction Stop; 'ok'")
        if "ok" in out:
            return {"killed": [f"PID {pid}"], "errors": []}
        return {"killed": [], "errors": [f"Could not kill PID {pid}"]}
    except ValueError:
        # It's a name — strip .exe suffix for matching, add it back for Stop-Process
        name = str(identifier).lower().replace(".exe", "")
        # Find matching processes first so we can report what we killed
        find = f"""
Get-Process | Where-Object {{ $_.Name -like '*{name}*' }} |
Select-Object @{{N='n';E={{$_.Name}}}},@{{N='id';E={{$_.Id}}}} |
ConvertTo-Json
"""
        killed, errors = [], []
        try:
            raw = _ps(find)
            if not raw:
                return {"killed": [], "errors": [f"No process found matching '{identifier}'"]}
            procs = json.loads(raw)
            if isinstance(procs, dict):
                procs = [procs]
            for p in procs:
                stop = _ps(f"Stop-Process -Id {p['id']} -Force -ErrorAction SilentlyContinue; 'ok'")
                if "ok" in stop:
                    killed.append(f"{p['n']} (PID {p['id']})")
                else:
                    errors.append(f"Failed to kill {p['n']}")
        except Exception as e:
            errors.append(str(e))
        if not killed and not errors:
            errors.append(f"No process found matching '{identifier}'")
        return {"killed": killed, "errors": errors}


# ── Launch application ─────────────────────────────────────────────────────────

def launch_application(app_name: str) -> dict:
    if IS_WSL:
        return _launch_wsl(app_name)

    # Native Windows
    app_map = {
        "notepad": "notepad.exe", "calculator": "calc.exe",
        "paint": "mspaint.exe", "explorer": "explorer.exe",
        "task manager": "taskmgr.exe", "cmd": "cmd.exe",
        "powershell": "powershell.exe", "edge": "msedge.exe",
        "chrome": "chrome.exe", "firefox": "firefox.exe",
        "word": "winword.exe", "excel": "excel.exe",
        "settings": "ms-settings:",
    }
    exe = app_map.get(app_name.lower().strip(), app_name)
    try:
        os.startfile(exe) if sys.platform == "win32" else subprocess.Popen(["xdg-open", exe])
        return {"success": True, "launched": exe}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _launch_wsl(app_name: str) -> dict:
    """Smart app launcher for WSL — tries hardcoded map, Start menu, then file search."""
    name = app_name.strip()
    name_lower = name.lower()

    # 1. Hardcoded common apps (instant, no search needed)
    app_map = {
        "notepad":      "notepad.exe",
        "calculator":   "calc.exe",
        "paint":        "mspaint.exe",
        "explorer":     "explorer.exe",
        "task manager": "taskmgr.exe",
        "cmd":          "cmd.exe",
        "powershell":   "powershell.exe",
        "edge":         r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "chrome":       r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "firefox":      r"C:\Program Files\Mozilla Firefox\firefox.exe",
        "word":         "winword.exe",
        "excel":        "excel.exe",
        "settings":     "ms-settings:",
    }
    if name_lower in app_map:
        exe = app_map[name_lower]
        _ps(f"Start-Process '{exe}'")
        return {"success": True, "launched": exe}

    # 2. Search Windows Start menu apps (UWP / Store apps like Minecraft Launcher)
    script_start = (
        f"$app = Get-StartApps | Where-Object {{ $_.Name -like '*{name}*' }} | Select-Object -First 1; "
        "if ($app) { Start-Process 'explorer.exe' \"shell:AppsFolder`$($app.AppID)\"; "
        "Write-Output \"launched:$($app.Name)\" } else { Write-Output 'notfound' }"
    )
    out = _ps(script_start)
    if out.startswith("launched:"):
        launched_name = out.replace("launched:", "").strip()
        return {"success": True, "launched": launched_name}

    # 3. Search common install directories for a matching .exe
    pf   = r"$env:ProgramFiles"
    pf86 = r"$env:ProgramFiles(x86)"
    lapp = r"$env:LOCALAPPDATA\Programs"
    wapp = r"$env:LOCALAPPDATA\Microsoft\WindowsApps"
    rapp = r"$env:APPDATA"
    script_find = f"""
$search_dirs = @('{pf}', '{pf86}', '{lapp}', '{wapp}', '{rapp}')
$exe = Get-ChildItem -Path $search_dirs -Filter '*{name}*.exe' -Recurse -ErrorAction SilentlyContinue |
    Where-Object {{ $_.Name -notlike '*uninstall*' -and $_.Name -notlike '*setup*' }} |
    Select-Object -First 1
if ($exe) {{ Start-Process $exe.FullName; Write-Output "launched:$($exe.Name)" }}
else {{ Write-Output 'notfound' }}
"""
    out2 = _ps(script_find)
    if out2.startswith("launched:"):
        launched_name = out2.replace("launched:", "").strip()
        return {"success": True, "launched": launched_name}

    return {"success": False, "error": f"Could not find '{name}'. Make sure it's installed and try the exact app name."}


# ── Network stats ──────────────────────────────────────────────────────────────

def get_network_stats() -> dict:
    if IS_WSL:
        return _network_stats_wsl()
    stats = psutil.net_io_counters()
    conns = psutil.net_connections()
    return {
        "bytes_sent_mb": round(stats.bytes_sent / 1e6, 2),
        "bytes_recv_mb": round(stats.bytes_recv / 1e6, 2),
        "packets_sent": stats.packets_sent,
        "packets_recv": stats.packets_recv,
        "established_connections": sum(1 for c in conns if c.status == "ESTABLISHED"),
        "total_connections": len(conns),
    }


def _network_stats_wsl() -> dict:
    script = """
$n = Get-NetAdapterStatistics | Measure-Object -Property ReceivedBytes,SentBytes -Sum
$conns = (Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue).Count
[PSCustomObject]@{
  bytes_recv_mb = [math]::Round(($n | Where-Object Property -eq ReceivedBytes).Sum/1MB, 2)
  bytes_sent_mb = [math]::Round(($n | Where-Object Property -eq SentBytes).Sum/1MB, 2)
  established_connections = $conns
} | ConvertTo-Json
"""
    try:
        data = json.loads(_ps(script))
        data["packets_sent"] = 0
        data["packets_recv"] = 0
        data["total_connections"] = data["established_connections"]
        return data
    except Exception:
        return {"bytes_sent_mb": 0, "bytes_recv_mb": 0,
                "established_connections": 0, "total_connections": 0}


# ── Startup programs ───────────────────────────────────────────────────────────

def get_startup_programs() -> list:
    if IS_WSL:
        script = """
$paths = @(
  'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run',
  'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run'
)
$out = @()
foreach ($p in $paths) {
  $k = Get-ItemProperty $p -ErrorAction SilentlyContinue
  if ($k) { $k.PSObject.Properties | Where-Object {$_.Name -notlike 'PS*'} |
    ForEach-Object { $out += [PSCustomObject]@{name=$_.Name;path=$_.Value} } }
}
$out | ConvertTo-Json
"""
        try:
            raw = _ps(script)
            if not raw:
                return []
            result = json.loads(raw)
            return result if isinstance(result, list) else [result]
        except Exception:
            return []
    if sys.platform != "win32":
        return []
    try:
        import winreg
        results = []
        for hive, path in [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        ]:
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


# ── Volume control ─────────────────────────────────────────────────────────────

def set_volume(level: int) -> dict:
    level = max(0, min(100, level))
    if IS_WSL:
        scalar = level / 100.0
        script = f"""
$vol = New-Object -ComObject WScript.Shell
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {{ int f(); int ff(); int fff(); int SetMasterVolumeLevelScalar(float f, System.Guid guid); }}
[Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
class MMDeviceEnumerator {{}}
'@ -ErrorAction SilentlyContinue
# Simpler: use nircmd if available, else WScript
$nircmd = "$env:WINDIR\\nircmd.exe"
if (Test-Path $nircmd) {{
  & $nircmd setsysvolume {int(scalar * 65535)}
}} else {{
  # PowerShell audio via shell
  $wsh = New-Object -ComObject WScript.Shell
  # mute/unmute approach not ideal; use SetMasterVolume via COM
  [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null
}}
'ok'
"""
        # Simpler reliable approach via nircmdc or just set via WScript mute hack
        simple = f"""
Add-Type -AssemblyName System.Windows.Forms
$vol = {level}
$cur = [System.Windows.Forms.SystemInformation]::MouseWheelScrollDelta
# Use Win32 API via inline C#
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class Audio {{
  [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
}}
"@
# Note: volume set via PowerShell AudioDevice object
$devices = [System.Runtime.InteropServices.Marshal]::GetActiveObject
'ok'
"""
        # Most reliable WSL volume control: use PowerShell with Win32 COM
        best = f"""
$volume = {level / 100.0}
Add-Type -TypeDefinition @"
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {{
  int _vt1(); int _vt2(); int _vt3();
  int SetMasterVolumeLevelScalar(float level, System.Guid evt);
  int GetMasterVolumeLevelScalar(out float level);
}}
[Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
[ClassInterface(ClassInterfaceType.None)]
class MMDeviceEnumeratorClass {{}}
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {{
  int EnumAudioEndpoints(int flow, int state, out System.IntPtr devices);
  int GetDefaultAudioEndpoint(int flow, int role, out System.IntPtr endpoint);
}}
"@ -ErrorAction SilentlyContinue
try {{
  $obj = [System.Runtime.InteropServices.Marshal]::CreateWrapperOfType(
    [System.Runtime.InteropServices.Marshal]::GetActiveObject("MMDeviceEnumerator"),
    [IMMDeviceEnumerator])
}} catch {{}}
# Fallback: nircmd
$nircmd = "$env:WINDIR\\nircmd.exe"
if (Test-Path $nircmd) {{
  & $nircmd setsysvolume {int(level / 100.0 * 65535)}
  'ok'
}} else {{
  'nircmd not found - volume control requires nircmd.exe in Windows folder'
}}
"""
        out = _ps(best)
        if "ok" in out:
            return {"success": True, "volume": level}
        return {"success": False, "error": out or "Volume control not available without nircmd.exe"}

    if sys.platform != "win32":
        return {"success": False, "error": "Windows only"}
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return {"success": True, "volume": level}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── File search ────────────────────────────────────────────────────────────────

def search_files(query: str, search_path: str = None, limit: int = 20) -> list:
    if IS_WSL:
        return _search_files_wsl(query, search_path, limit)
    if not search_path:
        search_path = os.path.expanduser("~") if sys.platform != "win32" else "C:\\"
    results = []
    query_lower = query.lower()
    try:
        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       {"__pycache__", "node_modules", ".git", "venv"}]
            for fname in files:
                if query_lower in fname.lower():
                    full_path = os.path.join(root, fname)
                    try:
                        stat = os.stat(full_path)
                        results.append({"name": fname, "path": full_path,
                                        "size_kb": round(stat.st_size / 1024, 1),
                                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")})
                    except Exception:
                        results.append({"name": fname, "path": full_path})
                    if len(results) >= limit:
                        return results
    except PermissionError:
        pass
    return results


def _search_files_wsl(query: str, search_path: str, limit: int) -> list:
    root = search_path or r"C:\Users"
    script = f"""
Get-ChildItem -Path '{root}' -Filter '*{query}*' -Recurse -ErrorAction SilentlyContinue |
Select-Object -First {limit} `
  @{{N='name';E={{$_.Name}}}},
  @{{N='path';E={{$_.FullName}}}},
  @{{N='size_kb';E={{[math]::Round($_.Length/1KB,1)}}}},
  @{{N='modified';E={{$_.LastWriteTime.ToString('yyyy-MM-dd HH:mm')}}}} |
ConvertTo-Json
"""
    try:
        raw = _ps(script)
        if not raw:
            return []
        result = json.loads(raw)
        return result if isinstance(result, list) else [result]
    except Exception:
        return []
