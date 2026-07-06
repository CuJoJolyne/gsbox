# file_utils — File & Path Operations

> Auto-generated code target: `common/file_utils.py`

## 1. Purpose

Cross-platform file/path utilities: existence checks, directory creation, temp dirs, path parsing, file read/write, HTTP download.

## 2. Public API

### 2.1 Path Checks

#### `is_exist_file(path: str) -> bool`
- **Description**: Check if path exists and is a file.
- **Edge Cases**: Returns False on any `OSError`/`ValueError`.

#### `is_exist_dir(path: str) -> bool`
- **Description**: Check if path exists and is a directory.

#### `is_net_file(path: str) -> bool`
- **Description**: Check if path starts with `http://` or `https://`.

### 2.2 Directory Operations

#### `mkdir_all(path: str) -> None`
- **Algorithm**: `os.makedirs(path, exist_ok=True)`

#### `create_temp_dir(base_name: str = "gsbox") -> str`
- **Description**: Create unique temp dir under system temp.
- **Algorithm**: `os.path.join(tempfile.gettempdir(), base_name, random_str)`
- **Returns**: Full path to created directory.

#### `remove_all(path: str) -> None`
- **Description**: Remove file or directory tree.
- **Algorithm**: `shutil.rmtree` for dirs, `os.remove` for files.

### 2.3 Path Parsing

#### `file_name(path: str) -> str`
- **Algorithm**: `pathlib.Path(path).name`

#### `file_name_without_ext(path: str) -> str`
- **Algorithm**: `pathlib.Path(path).stem`

#### `file_ext_name(path: str) -> str`
- **Algorithm**: `pathlib.Path(path).suffix` (includes dot)

#### `dir_name(path: str) -> str`
- **Algorithm**: `str(pathlib.Path(path).parent)`

### 2.4 File I/O

#### `write_file_bytes(path: str, data: bytes) -> None`
- **Description**: Write bytes to file, creating parents.
- **Algorithm**: `mkdir_all(dir_name(path))`, then `open(path, 'wb').write(data)`

#### `write_file_string(path: str, content: str) -> None`
- **Description**: Write string to file as UTF-8.

#### `read_file_bytes(path: str) -> bytes`
#### `read_file_string(path: str) -> str`

### 2.5 Utility

#### `get_file_size(path: str) -> int`
- **Algorithm**: `os.path.getsize(path)`

#### `copy_file(src: str, dst: str) -> None`
- **Algorithm**: `mkdir_all(dir_name(dst))`, then `shutil.copy2(src, dst)`

#### `endswith(path: str, suffix: str, ignore_case: bool = False) -> bool`
#### `startswith(path: str, prefix: str, ignore_case: bool = False) -> bool`

### 2.6 HTTP Download (no external deps)

#### `http_download(url: str, dest_path: str) -> None`
- **Algorithm**: `urllib.request.urlopen(url)`, then `shutil.copyfileobj` to file.
- **Edge Cases**: Network errors propagate as exceptions.

#### `read_remote_to_local(url: str) -> str`
- **Description**: Download remote file to temp dir, return local path.
- **Algorithm**: `create_temp_dir("gsbox_dl")` → `http_download` → return local path.

## 3. Edge Cases

| Scenario | Behavior |
|----------|----------|
| `is_exist_file` on nonexistent path | Returns False (no error) |
| `is_exist_file` on permission error | Returns False |
| `http_download` network error | Raises `urllib.error.URLError` |
| `create_temp_dir` parallel calls | Unique directories (random suffix) |

## 4. Examples

### 4.1 Path Basics

```python
from pygsbox.common.file_utils import file_ext_name, is_net_file
assert file_ext_name("/a/b/c.ply") == ".ply"
assert is_net_file("https://example.com/model.spz")
assert not is_net_file("./local.ply")
```

### 4.2 HTTP Download

```python
from pygsbox.common.file_utils import read_remote_to_local
# Returns local path after downloading
local = read_remote_to_local("https://example.com/model.ply")
assert os.path.exists(local)
```

## 5. Dependencies

| Module | Used for |
|--------|----------|
| os, pathlib, shutil | File/path operations |
| tempfile, random, string | Temp dir creation |
| urllib.request | HTTP download |

## 6. Agent Notes

- **No external HTTP library**: Use `urllib.request` from stdlib, not `requests`.
- **Temp dirs**: Create under `tempfile.gettempdir()/gsbox/<random>` for cleanup safety.
- **HTTP download**: No progress reporting in this layer; callers can wrap with `Progress` context.
