"""Minimal HID++ 2.0 transport over a Linux hidraw node.

Only what the G610 needs: long (20 byte) and very long (64 byte) reports,
feature index discovery through the root feature, and request/reply matching.
"""

from __future__ import annotations

import errno
import os
import select
import time
from typing import Callable

REPORT_LONG = 0x11
REPORT_VERY_LONG = 0x12
_SIZES = {REPORT_LONG: 20, REPORT_VERY_LONG: 64}
DEVICE_INDEX = 0xFF  # wired device
SOFTWARE_ID = 0x09   # tags our requests so replies can be told from notifications

ERRORS = {
    1: "unknown", 2: "invalid argument", 3: "out of range", 4: "hardware error",
    5: "not allowed", 6: "invalid feature index", 7: "invalid function",
    8: "busy", 9: "unsupported",
}


class HidppError(Exception):
    def __init__(self, feature_index: int, function: int, code: int):
        self.code = code
        super().__init__(
            f"HID++ error {code} ({ERRORS.get(code, '?')}) "
            f"from feature index {feature_index:#04x} function {function}")


class HidppTimeout(Exception):
    pass


class Hidpp:
    def __init__(self, path: str, on_report: Callable[[bytes], None] | None = None):
        self.path = path
        self.on_report = on_report
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self._features: dict[int, int | None] = {}

    def fileno(self) -> int:
        return self.fd

    def close(self) -> None:
        if self.fd >= 0:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = -1

    # -- raw I/O -----------------------------------------------------------

    def _read(self) -> bytes | None:
        try:
            return os.read(self.fd, 64)
        except BlockingIOError:
            return None

    def pump(self) -> None:
        """Read everything pending and hand it to on_report."""
        while True:
            data = self._read()
            if not data:
                return
            if self.on_report:
                self.on_report(data)

    def _write(self, data: bytes) -> None:
        deadline = time.monotonic() + 1.0
        while True:
            try:
                os.write(self.fd, data)
                return
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise OSError(errno.EIO, "hidraw write timed out")
                select.select([], [self.fd], [], 0.05)

    # -- requests ----------------------------------------------------------

    def request(self, feature_index: int, function: int, params: bytes = b"",
                very_long: bool = False, timeout: float = 1.0) -> bytes:
        """Send one request and return the parameters of its reply."""
        report = REPORT_VERY_LONG if very_long else REPORT_LONG
        size = _SIZES[report]
        if len(params) > size - 4:
            raise ValueError("too many parameters for report")
        func_sw = (function << 4) | SOFTWARE_ID
        msg = bytes([report, DEVICE_INDEX, feature_index, func_sw]) + bytes(params)
        self.pump()
        self._write(msg.ljust(size, b"\0"))

        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise HidppTimeout(
                    f"no reply from feature index {feature_index:#04x} function {function}")
            if not select.select([self.fd], [], [], left)[0]:
                continue
            data = self._read()
            if not data:
                continue
            if len(data) >= 6 and data[0] in (0x10, REPORT_LONG, REPORT_VERY_LONG):
                if data[2] == feature_index and data[3] == func_sw:
                    return data[4:]
                if data[2] == 0xFF and data[3] == feature_index and data[4] == func_sw:
                    raise HidppError(feature_index, function, data[5])
                if data[2] == 0x8F and data[3] == feature_index and data[4] == func_sw:
                    raise HidppError(feature_index, function, data[5])
            if self.on_report:
                self.on_report(data)

    def feature_index(self, feature_id: int) -> int | None:
        """Index of a feature on this device, or None when it has none."""
        if feature_id not in self._features:
            reply = self.request(0x00, 0, bytes([feature_id >> 8, feature_id & 0xFF]))
            self._features[feature_id] = reply[0] or None
        return self._features[feature_id]

    def ping(self) -> tuple[int, int]:
        reply = self.request(0x00, 1, bytes([0, 0, 0x5A]))
        return reply[0], reply[1]
