import os
import shutil
import tempfile
import random
import string
import pathlib
from typing import Optional, List


def is_exist_file(path: str) -> bool:
    try:
        return os.path.isfile(path)
    except (OSError, ValueError):
        return False


def is_exist_dir(path: str) -> bool:
    try:
        return os.path.isdir(path)
    except (OSError, ValueError):
        return False


def mkdir_all(path: str):
    os.makedirs(path, exist_ok=True)


def file_name(path: str) -> str:
    return pathlib.Path(path).name


def file_name_without_ext(path: str) -> str:
    p = pathlib.Path(path)
    return p.stem


def file_ext_name(path: str) -> str:
    return pathlib.Path(path).suffix


def dir_name(path: str) -> str:
    return str(pathlib.Path(path).parent)


def create_temp_dir(base_name: str = "gsbox") -> str:
    rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    tmp_dir = os.path.join(tempfile.gettempdir(), base_name, rand_str)
    mkdir_all(tmp_dir)
    return tmp_dir


def remove_all(path: str):
    if os.path.exists(path):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)


def copy_file(src: str, dst: str):
    mkdir_all(dir_name(dst))
    shutil.copy2(src, dst)


def copy_dir(src: str, dst: str):
    shutil.copytree(src, dst, dirs_exist_ok=True)


def write_file_bytes(path: str, data: bytes):
    mkdir_all(dir_name(path))
    with open(path, 'wb') as f:
        f.write(data)


def write_file_string(path: str, content: str):
    mkdir_all(dir_name(path))
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def read_file_bytes(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def read_file_string(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def get_file_size(path: str) -> int:
    return os.path.getsize(path)


def get_files(directory: str, suffix: str) -> List[str]:
    if not is_exist_dir(directory):
        return []
    paths = []
    for entry in os.scandir(directory):
        if entry.name.lower().endswith(suffix.lower()):
            paths.append(entry.path)
    paths.sort()
    return paths


def endswith(path: str, suffix: str, ignore_case: bool = False) -> bool:
    if ignore_case:
        return path.lower().endswith(suffix.lower())
    return path.endswith(suffix)


def startswith(path: str, prefix: str, ignore_case: bool = False) -> bool:
    if ignore_case:
        return path.lower().startswith(prefix.lower())
    return path.startswith(prefix)


def equals_ignore_case(s1: str, s2: str) -> bool:
    return s1.lower() == s2.lower()


def is_net_file(path: str) -> bool:
    return startswith(path, "https://") or startswith(path, "http://")


def http_download(url: str, dest_path: str):
    """Download a file from URL to local path."""
    import urllib.request
    import shutil
    mkdir_all(dir_name(dest_path))
    with urllib.request.urlopen(url) as resp:
        with open(dest_path, 'wb') as f:
            shutil.copyfileobj(resp, f)


def read_remote_to_local(url: str) -> str:
    """Download a remote file to a temp dir and return the local path."""
    import shutil
    tmp_dir = create_temp_dir("gsbox_dl")
    local = os.path.join(tmp_dir, file_name(url.split('?')[0]))
    if not local:
        local = os.path.join(tmp_dir, "download")
    http_download(url, local)
    return local
