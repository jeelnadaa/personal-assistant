"""Custom PyInstaller hook for webrtcvad to support webrtcvad-wheels metadata."""

from PyInstaller.utils.hooks import copy_metadata

try:
    datas = copy_metadata("webrtcvad")
except Exception:
    try:
        datas = copy_metadata("webrtcvad-wheels")
    except Exception:
        datas = []
