"""Explicit keyboard/UIA fallback for host file operations. Never captures images.

Not an internal FL save/render API. Inherits only window/dialog discovery from
the stable UI adapter; does not call its mouse-based save/open/export methods.
"""
import ctypes
from ctypes import wintypes
from pathlib import Path

from .desktop import FLDesktop, wait_for
from .native import inspect
from .workflow import WorkflowError, atomic_json, audio_integrity, copy_exclusive, digest, state_dir


def _foreground_process_name():
    """Process metadata only; never screenshots or inspection of authentication controls."""
    import ntpath
    user32,kernel32=ctypes.windll.user32,ctypes.windll.kernel32
    user32.GetForegroundWindow.restype=wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    pid=wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(),ctypes.byref(pid))
    kernel32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel32.OpenProcess.restype=wintypes.HANDLE
    handle=kernel32.OpenProcess(0x1000,False,pid.value)  # query limited information only
    if not handle:return None
    try:
        kernel32.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
        size=wintypes.DWORD(32768);buffer=ctypes.create_unicode_buffer(size.value)
        return ntpath.basename(buffer.value).lower() if kernel32.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)) else None
    finally:
        kernel32.CloseHandle.argtypes=[wintypes.HANDLE]
        kernel32.CloseHandle(handle)


def require_interactive_desktop():
    if _foreground_process_name() in {'lockapp.exe','logonui.exe'}:
        raise WorkflowError('DESKTOP_LOCKED','Windows is locked; no GUI input sent. Unlock normally to resume. No automated unlocking attempted.')


class HostFiles(FLDesktop):
    def focus(self,expected_title=None):
        require_interactive_desktop()
        return super().focus(expected_title)

    def focus_control(self,target):
        """Native thread focus; pywinauto Win32 set_focus may move the pointer."""
        user32,kernel32=ctypes.windll.user32,ctypes.windll.kernel32
        user32.SetFocus.argtypes=[wintypes.HWND];user32.SetFocus.restype=wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        thread=user32.GetWindowThreadProcessId(target.handle,None)
        current=kernel32.GetCurrentThreadId()
        user32.AttachThreadInput.argtypes=[wintypes.DWORD,wintypes.DWORD,wintypes.BOOL]
        attached=current!=thread and bool(user32.AttachThreadInput(current,thread,True))
        try:user32.SetFocus(target.handle)
        finally:
            if attached:user32.AttachThreadInput(current,thread,False)
        class GuiThreadInfo(ctypes.Structure):
            _fields_=[('cbSize',wintypes.DWORD),('flags',wintypes.DWORD)]+[(n,wintypes.HWND) for n in
                ('hwndActive','hwndFocus','hwndCapture','hwndMenuOwner','hwndMoveSize','hwndCaret')]+[('rcCaret',wintypes.RECT)]
        info=GuiThreadInfo();info.cbSize=ctypes.sizeof(info)
        user32.GetGUIThreadInfo.argtypes=[wintypes.DWORD,ctypes.POINTER(GuiThreadInfo)]
        user32.IsChild.argtypes=[wintypes.HWND,wintypes.HWND]
        if not user32.GetGUIThreadInfo(thread,ctypes.byref(info)) or not (info.hwndFocus==target.handle or user32.IsChild(target.handle,info.hwndFocus)):
            raise WorkflowError('FOCUS_LOST','Native editor focus could not be verified; no keys sent')

    def _keys(self, keys, target=None, *, unicode_text=False):
        require_interactive_desktop()
        from .pyscript_trigger import force_focus
        from pywinauto.keyboard import send_keys
        target = self.main if target is None else target
        if not target.is_visible() or target.process_id() != self.pid:
            raise WorkflowError('FOCUS_LOST', 'No keys sent to an unverified target')
        # FL editor panes can become the foreground HWND even though Windows
        # refuses SetForegroundWindow(child). Activate the top-level host first.
        activation = self.main if target.class_name() in {'TEventEditForm','TStepSeqForm','TFXForm'} else target
        user32=ctypes.windll.user32
        user32.GetForegroundWindow.restype=wintypes.HWND
        pid=wintypes.DWORD()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(),ctypes.byref(pid))
        if pid.value!=self.pid:
            if not force_focus(activation.handle):
                raise WorkflowError('FOCUS_LOST','No keys sent: host activation failed')
        elif activation is not self.main and user32.GetForegroundWindow()!=activation.handle:
            # Never tap Alt while a popup is open: it can dismiss the picker.
            user32.SetForegroundWindow(activation.handle)
        if target is not activation:
            self.focus_control(target)
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
        if pid.value != self.pid:
            raise WorkflowError('FOCUS_LOST', 'Foreground belongs to another process; no keys sent')
        if activation is not self.main and user32.GetForegroundWindow()!=activation.handle:
            raise WorkflowError('FOCUS_LOST','Expected native popup is not foreground; no keys sent')
        # Text must bypass the active IME; physical letter keys can compose
        # Chinese words instead of the requested plugin name. Shortcuts retain VKs.
        send_keys(keys,vk_packet=unicode_text,with_spaces=True)

    def _playlist_keys(self, keys, expected_title):
        self.focus(expected_title)
        if self.dialogs():
            raise WorkflowError('GUI_BLOCKED', 'Existing modal dialog; no automatic dismissal')
        try:playlist=self.playlist()
        except WorkflowError as exc:
            if exc.code!='GUI_LAYOUT':raise
            self._keys('{F5}')
            def visible():
                try:return self.playlist()
                except WorkflowError as exc:
                    if exc.code=='GUI_LAYOUT':return None
                    raise
            playlist=wait_for(visible,description='Playlist visible for file shortcut')
        self.focus_control(playlist)
        self._keys(keys, playlist)

    def channel_rack(self):
        def visible():
            rows=[w for w in self.main.descendants() if w.class_name()=='TStepSeqForm' and w.is_visible()]
            return rows[0] if len(rows)==1 else None
        if visible() is None:self._keys('{F6}')
        return wait_for(visible,description='unique visible Channel Rack')

    def _own(self, path):
        session=dict(path=str(path), sha256=digest(path),title=self.main.window_text(),process_id=self.pid)
        atomic_json(state_dir()/'host-file-session.json',session)
        # Both adapters own the same actual native save, not separate projects.
        atomic_json(state_dir()/'desktop-session.json',session)

    def _require_owned(self, expected_title):
        import json
        path = state_dir()/'host-file-session.json'
        if not path.exists():
            raise WorkflowError('NO_OWNED_SESSION', 'First Save As to a new independent FLP using this adapter')
        session = json.loads(path.read_text(encoding='utf8'))
        if session['process_id'] != self.pid or session['title'] != expected_title or self.main.window_text() != expected_title or digest(session['path']) != session['sha256']:
            raise WorkflowError('SESSION_CHANGED', 'Owned saved project identity differs')
        return session

    def save_as_no_image(self, destination, expected_title):
        path = Path(destination).resolve()
        if path.suffix.lower() != '.flp' or path.exists():
            raise WorkflowError('OVERWRITE_REFUSED', 'A new .flp destination is required')
        path.parent.mkdir(parents=True, exist_ok=True)
        self._playlist_keys('^+s', expected_title)
        self.file_dialog(path)  # UIA ValuePattern/InvokePattern and file-type guard
        wait_for(lambda: path.is_file() and self.main.is_enabled() and path.name.lower() in self.main.window_text().lower(), description='native FL Save As')
        saved = inspect(path)
        self._own(path)
        return dict(ok=True, verified=True, execution_kind='keyboard_UIA_fallback', path=str(path),
                    title=self.main.window_text(), saved_state=saved, screenshots=0, mouse_operations=0)

    def reopen_copy(self, source, destination, preserve_current_to, expected_title):
        source, destination, preserve = map(lambda p: Path(p).resolve(), (source,destination,preserve_current_to))
        inspect(source)
        if len({source,destination,preserve}) != 3 or any(p.suffix.lower() != '.flp' for p in (source,destination,preserve)) or destination.exists() or preserve.exists():
            raise WorkflowError('OVERWRITE_REFUSED', 'Source and two fresh distinct FLP paths required')
        self._require_owned(expected_title)
        preservation = self.save_as_no_image(preserve, expected_title)
        copied = copy_exclusive(source,destination)
        self._playlist_keys('^o',preservation['title'])
        self.file_dialog(destination)
        wait_for(lambda: self.main.is_enabled() and destination.name.lower() in self.main.window_text().lower(), timeout=30, description='opened independent FLP copy')
        from .connection import get_bridge,FLBridgeError
        def bridge_ready():
            try:return bool(get_bridge().call('ping').get('protocol_version'))
            except FLBridgeError:return False
        wait_for(bridge_ready,timeout=45,description='FL bridge ready after project/plugin initialization')
        self._own(destination)
        return dict(ok=True, verified=True, execution_kind='keyboard_UIA_fallback', path=str(destination),
            title=self.main.window_text(), preserved=preservation['path'], source_copy=copied,
            limitation='Window/file identity verified; independently reread plugin values to verify persistence',
            bridge_ready=True,screenshots=0,mouse_operations=0)

    def export_wav_no_image(self,destination,expected_title,minimum_seconds=.05,maximum_seconds=3600,prepare_only=False):
        path=Path(destination).resolve()
        if path.suffix.lower()!='.wav' or path.exists():
            raise WorkflowError('OVERWRITE_REFUSED','A fresh WAV destination is required')
        self._require_owned(expected_title)
        path.parent.mkdir(parents=True,exist_ok=True)
        self._playlist_keys('^r',expected_title)
        self.file_dialog(path)
        def render_form():
            forms=[w for w in self.win32.windows(process=self.pid,class_name='TWAVRenderForm') if w.is_visible()]
            if len(forms)==1 and path.name.lower() in forms[0].window_text().lower():return forms[0]
        form=wait_for(render_form,description='correct FL WAV render form')
        if prepare_only:
            return dict(ok=True,verified=False,phase='render_dialog_open_only',destination=str(path),
                handle=str(form.handle),execution_kind='keyboard_UIA_fallback',
                limitation='No rendering started. Inspect actual settings, start through GUI and verify actual WAV separately.')
        self._keys('{ENTER}',form)  # verified native default Start action; no blind repeated Enter
        wait_for(lambda: path.is_file() and not form.is_visible() and self.main.is_enabled(),timeout=120,description='FL render completion')
        result=audio_integrity(path,minimum_seconds,maximum_seconds)
        return dict(**result,execution_kind='keyboard_UIA_fallback',screenshots=0,mouse_operations=0,
            limitation='Existing render settings inherited; actual audio format/duration reported, settings not configured. No subjective listening.')
