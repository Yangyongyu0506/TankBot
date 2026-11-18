"""Editable files are drafts; only an explicit Start captures an immutable revision."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from subprocess import Popen, DEVNULL
import sys
import threading
import uuid

from tankbot_protocol.wire import strict_loads
from .workspace import validate_files

ROOT = Path(__file__).resolve().parents[2]


def source_hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest() if value is not None else None


class EditableProject:
    def __init__(self, store, options):
        self.store, self.options = store, options
        self.directory = store.directory.absolute()
        self.root = self.directory / options['working_directory']
        self.state = self.directory / 'EDITABLE.json'
        self.recovery = self.directory / 'editable-recovery'

    @staticmethod
    def _safe(path, directory=False):
        mode = path.lstat()
        if stat.S_ISLNK(mode.st_mode) or (not directory and (not stat.S_ISREG(mode.st_mode) or mode.st_nlink != 1)):
            raise ValueError('UNSAFE_EDITOR_PATH: ' + path.name)
        if directory and not stat.S_ISDIR(mode.st_mode):
            raise ValueError('UNSAFE_EDITOR_DIRECTORY: ' + path.name)

    def _parents(self, path):
        self._safe(self.directory, True)
        for parent in reversed(path.relative_to(self.directory).parents):
            directory = self.directory / parent
            if not directory.exists() and not directory.is_symlink():
                directory.mkdir()
            self._safe(directory, True)

    def _read(self):
        self._safe(self.root, True)
        files, entries = {}, 0
        for directory, folders, names in os.walk(self.root, followlinks=False):
            parent = Path(directory)
            if len(parent.relative_to(self.root).parts) > self.options['max_scan_depth']:
                raise ValueError('EDITOR_TREE_LIMIT: 目录层数过多')
            folders[:] = [name for name in folders if not name.startswith('.') and name != '__pycache__']
            for name in [*folders, *names]:
                if name.startswith('.'):
                    continue
                entries += 1
                if entries > self.options['max_scan_entries']:
                    raise ValueError('EDITOR_TREE_LIMIT: 文件或目录数量过多')
                path = parent / name
                if name in folders:
                    self._safe(path, True)
                    continue
                self._safe(path)
                if path.suffix not in ('.py', '.json', '.md'):
                    continue
                if path.stat().st_size > self.store.limits['max_source_bytes']:
                    raise ValueError('WORKSPACE_BYTE_LIMIT: ' + str(path.relative_to(self.root)))
                files[path.relative_to(self.root).as_posix()] = path.read_bytes().decode('utf-8')
                if len(files) > self.store.limits['max_files']:
                    raise ValueError('WORKSPACE_FILE_LIMIT')
        # Syntax/Contract errors belong to preflight, not to the draft reader.
        validate_files(files, self.store.limits)
        return files

    def _record(self, snapshot):
        value = {'version': 1, 'revision': snapshot['revision'],
                 'files': {path: source_hash(source) for path, source in snapshot['files'].items()}}
        temporary = self.state.with_name('.editable-' + uuid.uuid4().hex + '.tmp')
        if self.state.exists() or self.state.is_symlink():
            self._safe(self.state)
        try:
            with temporary.open('xb') as stream:
                stream.write(json.dumps(value, sort_keys=True).encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.state)
        finally:
            temporary.unlink(missing_ok=True)

    def _write(self, name, previous, incoming):
        path = self.root / name
        self._parents(path)
        if previous is not None:
            self._parents(self.recovery / 'placeholder')
            backup = self.recovery / (uuid.uuid4().hex + '-' + path.name)
            self._safe(path)
            path.rename(backup)
            # Keep the moved file, including writes through an already-open editor
            # descriptor. Never replace a new save made at the original pathname.
            if backup.read_bytes().decode('utf-8') != previous:
                if not path.exists():
                    with path.open('xb') as target:
                        target.write(backup.read_bytes())
                raise ValueError('EDITOR_CONCURRENT_SAVE: ' + name + '; 原文件保留于 ' + str(backup))
        if incoming is not None:
            try:
                with path.open('xb') as stream:
                    stream.write(incoming.encode('utf-8'))
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError as error:
                raise ValueError('EDITOR_CONCURRENT_SAVE: ' + name + '; 未覆盖外部保存') from error

    def refresh(self):
        """Rebase unchanged files; divergent edits cause a non-destructive conflict."""
        with self.store.transaction():
            current = self.store.read()
            if self.root.is_symlink():
                raise ValueError('UNSAFE_EDITOR_PATH')
            if not self.root.exists():
                self.root.mkdir()
            if self.state.exists() or self.state.is_symlink():
                self._safe(self.state)
                state = strict_loads(self.state.read_bytes())
                if (not isinstance(state, dict) or set(state) != {'version', 'revision', 'files'}
                        or type(state['version']) is not int or state['version'] != 1 or not isinstance(state['files'], dict)
                        or any(not isinstance(k, str) or not isinstance(v, str) or len(v) != 64 for k, v in state['files'].items())):
                    raise ValueError('INVALID_EDITOR_STATE: 源码未改动')
                base = state['files']
            else:
                base = {}
            local = self._read() if any(self.root.iterdir()) else {}
            changes, conflicts = [], []
            for name in sorted(set(base) | set(local) | set(current['files'])):
                before, disk = base.get(name), source_hash(local.get(name))
                canonical = source_hash(current['files'].get(name))
                if disk != before and canonical != before and disk != canonical:
                    conflicts.append(name)
                elif disk == before and canonical != disk:
                    changes.append((name, local.get(name), current['files'].get(name)))
            if conflicts:
                raise ValueError('EDITOR_MERGE_CONFLICT: ' + ', '.join(conflicts) + '；磁盘文件与历史均保留，请先备份并合并')
            for change in changes:
                self._write(*change)
            self._record(current)
            return current

    def capture(self):
        with self.store.transaction():
            self.refresh()
            current = self.store.read()
            files = self._read()
            # Catch ordinary atomic-save races rather than freezing a mixed scan.
            if files != self._read():
                raise ValueError('EDITOR_CONCURRENT_SAVE: 请完成保存后再点击 Start')
            changes = {path: files.get(path) for path in set(files) | set(current['files'])
                       if files.get(path) != current['files'].get(path)}
            snapshot = self.store.edit(current['revision'], changes) if changes else current
            self._record(snapshot)
            return snapshot

    def open(self, lesson):
        self.refresh()
        # Editor support files are not player sources and never enter a Runtime.
        directory = self.root / '.vscode'
        self._parents(directory / 'settings.json')
        settings = directory / 'settings.json'
        if not settings.exists() and not settings.is_symlink():
            with settings.open('x', encoding='utf-8') as stream:
                json.dump({'python.defaultInterpreterPath': sys.executable,
                           'python.analysis.extraPaths': [str(ROOT / 'sdk/python')]}, stream, indent=2)
        else:
            self._safe(settings)
        executable = shutil.which(self.options['executable'])
        if not executable:
            raise ValueError('VSCODE_NOT_FOUND: 请安装 VS Code 并将 code 加入 PATH，或配置 desktop.yaml 的 editor.executable。代码目录：' + str(self.root))
        paths = lesson.get('edit_files', []) or [entry['path'] for entry in lesson.get('functions', [])]
        allowed = self.store.read()['files']
        paths = [str(self.root / path) for path in paths if path in allowed and (self.root / path).is_file()]
        command = [executable, *self.options['arguments'], str(self.root), *paths]
        # No shell, arbitrary caller arguments, wait-for-editor, or process ownership.
        # VS Code may remain open after the game exits; saved drafts remain on disk.
        child = Popen(command, cwd=self.root, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL)
        threading.Thread(target=child.wait, daemon=True).start()
        return {'requested': True, 'directory': str(self.root), 'files': paths,
                'message': '已请求 VS Code 打开本关代码；保存后回游戏点击 Start。'}
