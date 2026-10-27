"""Read-only Windows path discovery; never change FL settings or scan whole drives."""
from __future__ import annotations

import os
from pathlib import Path


def documents_dirs():
    candidates = []
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                value, _ = winreg.QueryValueEx(key, "Personal")
                candidates.append(Path(os.path.expandvars(value)))
        except OSError:
            pass
    candidates += [Path.home() / "Documents", Path.home()]
    return list(dict.fromkeys(candidates))


def fl_user_dirs():
    for doc in documents_dirs():
        root = doc / "Image-Line"
        if root.is_dir():
            yield from sorted(root.glob("FL Studio*"), reverse=True)


def fl_install_dirs():
    candidates = []
    explicit = os.environ.get("FLSTUDIO_MCP_INSTALL_DIR")
    if explicit:
        candidates.append(Path(explicit))
    if os.name == "nt":
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for flags in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                          winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Image-Line", 0, flags) as root:
                        for i in range(winreg.QueryInfoKey(root)[0]):
                            name = winreg.EnumKey(root, i)
                            if not name.lower().startswith("fl studio"):
                                continue
                            with winreg.OpenKey(root, name) as key:
                                for field in ("InstallPath", "InstallDir", "Path"):
                                    try:
                                        value, _ = winreg.QueryValueEx(key, field)
                                        candidates.append(Path(os.path.expandvars(value)))
                                    except OSError:
                                        pass
                except OSError:
                    pass
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for flags in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                          winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive,
                            r"Software\Microsoft\Windows\CurrentVersion\Uninstall", 0, flags) as root:
                        for i in range(winreg.QueryInfoKey(root)[0]):
                            with winreg.OpenKey(root, winreg.EnumKey(root, i)) as key:
                                try:
                                    name, _ = winreg.QueryValueEx(key, "DisplayName")
                                    if not str(name).lower().startswith("fl studio"):
                                        continue
                                    try:
                                        value, _ = winreg.QueryValueEx(key, "InstallLocation")
                                        if value:
                                            candidates.append(Path(value))
                                    except OSError:
                                        pass
                                    icon, _ = winreg.QueryValueEx(key, "DisplayIcon")
                                    icon_path = Path(str(icon).rsplit(",", 1)[0].strip('"'))
                                    candidates.extend(icon_path.parents)
                                except OSError:
                                    pass
                except OSError:
                    pass
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = Path(os.environ.get(env, "C:/Program Files")) / "Image-Line"
        if base.is_dir():
            candidates.extend(sorted(base.glob("FL Studio*"), reverse=True))
    return [p for p in dict.fromkeys(candidates) if (p / "Data" / "Patches").is_dir()]
