"""Toolchain detection and environment setup.

Auto-detects OS and EDA tool locations (iverilog, yosys, vvp) to provide
correct PATH and environment variables. Handles Windows + oss-cad-suite
quirks discovered during real project usage.
"""

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# Common oss-cad-suite install locations per OS
_OSS_CAD_SEARCH_PATHS = {
    "Windows": [
        "C:/oss-cad-suite",
        os.path.expanduser("~/oss-cad-suite"),
    ],
    "Linux": [
        "/opt/oss-cad-suite",
        os.path.expanduser("~/oss-cad-suite"),
    ],
    "Darwin": [
        "/opt/homebrew/opt/oss-cad-suite",
        os.path.expanduser("~/oss-cad-suite"),
    ],
}


@dataclass
class ToolInfo:
    """Information about a detected EDA tool."""
    name: str
    path: Optional[str] = None
    version: Optional[str] = None
    available: bool = False


@dataclass
class ToolchainEnv:
    """Resolved toolchain environment."""
    tools: Dict[str, ToolInfo] = field(default_factory=dict)
    env_vars: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    @property
    def path_prefix(self) -> str:
        """Return PATH prefix string for shell commands."""
        return self.env_vars.get("PATH_PREFIX", "")

    def shell_env(self) -> Dict[str, str]:
        """Return a copy of os.environ with toolchain paths prepended."""
        env = os.environ.copy()
        prefix = self.path_prefix
        if prefix:
            env["PATH"] = prefix + os.pathsep + env.get("PATH", "")
        return env


def detect_toolchain() -> ToolchainEnv:
    """Auto-detect EDA toolchain and return environment setup."""
    result = ToolchainEnv()
    system = platform.system()

    # Try to find oss-cad-suite
    oss_root = _find_oss_cad_suite(system)
    if oss_root:
        bin_dir = os.path.join(oss_root, "bin")
        lib_dir = os.path.join(oss_root, "lib")

        path_parts = [bin_dir]
        # Windows needs lib dir for DLLs (exit code 127 without it)
        if system == "Windows":
            path_parts.append(lib_dir)
            result.warnings.append(
                f"Windows detected: adding {lib_dir} to PATH for DLL resolution"
            )

        result.env_vars["PATH_PREFIX"] = os.pathsep.join(path_parts)
        result.env_vars["OSS_CAD_SUITE"] = oss_root

    # Detect individual tools
    env = result.shell_env()
    for tool_name in ("iverilog", "vvp", "yosys", "verilator", "verible-verilog-lint"):
        info = _detect_tool(tool_name, env)
        result.tools[tool_name] = info
        if not info.available:
            result.warnings.append(f"{tool_name} not found in PATH")

    # Windows-specific warnings
    if system == "Windows":
        result.warnings.append(
            "Windows: avoid cmd.exe /c wrappers — run tools directly from bash/shell"
        )

    return result


def _find_oss_cad_suite(system: str) -> Optional[str]:
    """Search for oss-cad-suite installation directory."""
    search_paths = _OSS_CAD_SEARCH_PATHS.get(system, [])
    for p in search_paths:
        bin_dir = os.path.join(p, "bin")
        if os.path.isdir(bin_dir):
            return p
    return None


def _detect_tool(name: str, env: Dict[str, str]) -> ToolInfo:
    """Detect a single tool and get its version."""
    info = ToolInfo(name=name)

    # Check if tool exists
    exe_name = f"{name}.exe" if platform.system() == "Windows" else name
    path = shutil.which(exe_name, path=env.get("PATH"))
    if not path:
        return info

    info.path = path
    info.available = True

    # Try to get version
    try:
        if name == "iverilog":
            r = subprocess.run([path, "-V"], capture_output=True, text=True, timeout=5, env=env)
            if r.stdout:
                info.version = r.stdout.split('\n')[0].strip()
        elif name == "yosys":
            r = subprocess.run([path, "-V"], capture_output=True, text=True, timeout=5, env=env)
            if r.stdout:
                info.version = r.stdout.strip()
        elif name == "vvp":
            r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5, env=env)
            if r.stdout:
                info.version = r.stdout.split('\n')[0].strip()
        elif name == "verilator":
            r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5, env=env)
            if r.stdout:
                info.version = r.stdout.strip()
        elif name == "verible-verilog-lint":
            r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5, env=env)
            if r.stdout:
                info.version = r.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass

    return info
