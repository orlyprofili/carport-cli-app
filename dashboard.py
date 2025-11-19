#!/usr/bin/env python3
"""
G-Love Dashboard (Qt/PySide6)

PySide6 rewrite of the original Tk/TkAgg dashboard. Embeds the 3D motion
visualizer next to a CLI console and a monitor log pane. Supports USB serial
and BLE (Nordic UART Service).

Key performance notes:
- Qt event loop with QTimer for steady 30 Hz plot updates and queue draining.
- Matplotlib QtAgg canvas with constrained re-draws (no cache_frame_data).
- All I/O stays off the GUI thread; GUI pulls from thread-safe queues.

Usage:
  python dashboard_qt.py                               # auto-detect serial
  python dashboard_qt.py --ble --ble-name "G-Love"     # BLE
  python dashboard_qt.py --ble --show-logs
  python dashboard_qt.py --log-tags FUSION,MIDI

Dependencies:
  pip install PySide6 matplotlib numpy pyserial bleak
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import glob
import json
import math
import queue
import re
import signal
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Optional, Tuple, TYPE_CHECKING, cast

import numpy as np

# ----------------------------- Regex and constants ----------------------------

# Font configuration
MONOSPACE_FONT_SIZE = 13

FUSION_Q_RE = re.compile(r"FUSION\s+q:\[([^\]]+)\]")
SFLP_Q_RE = re.compile(r"SFLP\s+q:\[([^\]]+)\]")
POSITION_RE = re.compile(r"POS\s*:\[([^\]]+)\]")
MAG_RE = re.compile(r"M:\[([^\]]+)\]")
FLEX_RE = re.compile(
    r"FLEX:\s*Flex value changed:\s*(\d+)\s*->\s*(\d+)\s*\(raw median:\s*(\d+),\s*MIDI:\s*(\d+)\)",
    re.IGNORECASE,
)

NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
BLE_DEFAULT_NAME_HINT = "G-Love"
DEFAULT_WRITE_CHUNK = 20

LOG_LINE_RE = re.compile(
    r"^(?P<level>[EWIDV]) \((?P<timestamp>\d+)\) (?P<tag>[^:]+): (?P<message>.*)$"
)
LOG_PREFIXES = tuple(f"{lvl} (" for lvl in "EWIDV")
ANSI_PREFIX_RE = re.compile(r"^(?:\x1b\[[0-9;]*m)+")
SUPPRESSED_MONITOR_TAGS = {"FUSION", "MOTION", "FLEX"}
BATT_RE = re.compile(r"BATT:\s*([0-9.]+)\s*%\s*([0-9.]+)\s*V")
RSSI_RE = re.compile(r"RSSI[:=]\s*(-?\d+)\s*dBm", re.IGNORECASE)
PUNCH_RE = re.compile(
    r"Punch detected:\s*([0-9.+-]+)\s*m/s\s*hv=([0-9.+-]+)\s*deg\s*vv=([0-9.+-]+)\s*deg",
    re.IGNORECASE,
)

LAYOUT_STATE_FILE = Path(__file__).resolve().parent / ".dashboard_layout_qt.json"

# ----------------------------- Utility functions ------------------------------


def parse_quat(s: str) -> Optional[Tuple[float, float, float, float]]:
    try:
        parts = [p.strip() for p in s.split(",")]
        if len(parts) != 4:
            return None
        q = np.array(list(map(float, parts)), dtype=float)
        n = np.linalg.norm(q)
        if n == 0 or not np.isfinite(n):
            return None
        q /= n
        return (float(q[0]), float(q[1]), float(q[2]), float(q[3]))
    except Exception:
        return None


def parse_vec3(s: str) -> Optional[Tuple[float, float, float]]:
    try:
        parts = [p.strip() for p in s.split(",")]
        if len(parts) != 3:
            return None
        vec = tuple(float(p) for p in parts)
        if not np.isfinite(np.array(vec)).all():
            return None
        return vec  # type: ignore[return-value]
    except Exception:
        return None


def quat_to_rotation_matrix(q: Tuple[float, float, float, float]) -> np.ndarray:
    w, x, y, z = q
    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z
    two = 2.0
    return np.array(
        [
            [1.0 - two * (yy + zz), two * (xy - wz), two * (xz + wy)],
            [two * (xy + wz), 1.0 - two * (xx + zz), two * (yz - wx)],
            [two * (xz - wy), two * (yz + wx), 1.0 - two * (xx + yy)],
        ],
        dtype=float,
    )


def find_default_port() -> Optional[str]:
    preferred_patterns = [
        "/dev/tty.usbmodem*",
        "/dev/tty.SLAB*",
        "/dev/ttyUSB*",
        "/dev/cu.usb*",
        "/dev/cu.SLAB*",
    ]
    candidates: list[str] = []
    for pat in preferred_patterns:
        candidates.extend(glob.glob(pat))
    if not candidates:
        candidates = glob.glob("/dev/tty.*") + glob.glob("/dev/cu.*")
    filtered = [
        p
        for p in candidates
        if not any(x in p.lower() for x in ["bluetooth", "airpods", "iap", "modem"])
    ]
    ports = filtered or candidates
    ports = sorted(set(ports))
    return ports[0] if ports else None


def _strip_ansi_prefix(text: str) -> str:
    return ANSI_PREFIX_RE.sub("", text)


# ----------------------------- Log filtering ----------------------------------


class _LogLineFilter:
    def __init__(self, show_logs: bool, allowed_tags: Optional[set[str]]):
        self._show_logs = show_logs
        self._allowed_tags = (
            {tag.strip().upper() for tag in allowed_tags} if allowed_tags else None
        )

    def allows(self, match: Optional[re.Match]) -> bool:
        if match is None:
            return True
        if self._show_logs:
            return True
        if self._allowed_tags is None:
            return False
        tag = match.group("tag").strip().upper()
        return tag in self._allowed_tags


# ----------------------------- Telemetry model --------------------------------


class TelemetryState:
    def __init__(self):
        self._lock = threading.Lock()
        self._latest_fusion: Optional[Tuple[float, float, float, float]] = None
        self._latest_sflp: Optional[Tuple[float, float, float, float]] = None
        self._latest_position: Optional[np.ndarray] = None
        self._position_ts = 0.0
        self._latest_mag: Optional[np.ndarray] = None
        self._mag_ts = 0.0
        self._last_telemetry_update = 0.0
        self._last_punch: Optional[Tuple[float, float, float]] = None
        self._last_punch_ts = 0.0
        self._flex_value = None
        self._flex_raw_median = None
        self._flex_midi = None
        self._flex_ts = 0.0

    def ingest_line(self, line: str) -> None:
        updated = False
        fusion_match = FUSION_Q_RE.search(line)
        if fusion_match:
            q = parse_quat(fusion_match.group(1))
            if q:
                with self._lock:
                    self._latest_fusion = q
                    self._last_telemetry_update = time.time()
                updated = True

        sflp_match = SFLP_Q_RE.search(line)
        if sflp_match:
            q = parse_quat(sflp_match.group(1))
            if q:
                with self._lock:
                    self._latest_sflp = q
                    self._last_telemetry_update = time.time()
                updated = True

        pos_match = POSITION_RE.search(line)
        if pos_match:
            pos = parse_vec3(pos_match.group(1))
            if pos is not None:
                arr = np.array(pos, dtype=float)
                with self._lock:
                    self._latest_position = arr
                    self._position_ts = time.time()
                    self._last_telemetry_update = self._position_ts
                updated = True

        mag_match = MAG_RE.search(line)
        if mag_match:
            mag = parse_vec3(mag_match.group(1))
            if mag is not None:
                arr = np.array(mag, dtype=float)
                with self._lock:
                    self._latest_mag = arr
                    self._mag_ts = time.time()
                    self._last_telemetry_update = self._mag_ts
                updated = True

        punch_match = PUNCH_RE.search(line)
        if punch_match:
            try:
                velocity = float(punch_match.group(1))
                horizontal = float(punch_match.group(2))
                vertical = float(punch_match.group(3))
            except ValueError:
                velocity = float("nan")
                horizontal = float("nan")
                vertical = float("nan")

            if np.isfinite(
                np.array([velocity, horizontal, vertical], dtype=float)
            ).all():
                with self._lock:
                    self._last_punch = (velocity, horizontal, vertical)
                    self._last_punch_ts = time.time()
                    self._last_telemetry_update = self._last_punch_ts
                updated = True

        flex_match = FLEX_RE.search(line)
        if flex_match:
            try:
                _old = int(flex_match.group(1))
                new_val = int(flex_match.group(2))
                raw_median = int(flex_match.group(3))
                midi_val = int(flex_match.group(4))
            except ValueError:
                new_val = None
                raw_median = None
                midi_val = None
            if None not in (new_val, raw_median, midi_val):
                with self._lock:
                    self._flex_value = new_val
                    self._flex_raw_median = raw_median
                    self._flex_midi = midi_val
                    self._flex_ts = time.time()
                    self._last_telemetry_update = self._flex_ts
                updated = True

        if not updated:
            with self._lock:
                self._last_telemetry_update = time.time()

    def snapshot(
        self,
    ) -> tuple[
        Optional[Tuple[float, float, float, float]],
        Optional[Tuple[float, float, float, float]],
        Optional[Tuple[float, float, float, float]],
        Optional[str],
        Optional[np.ndarray],
        float,
        Optional[Tuple[float, float, float]],
        float,
        Optional[np.ndarray],
        float,
        Optional[int],
        Optional[int],
        Optional[int],
        float,
    ]:
        with self._lock:
            fusion = self._latest_fusion
            sflp = self._latest_sflp
            position = (
                None
                if self._latest_position is None
                else np.array(self._latest_position, copy=True)
            )
            ts = self._position_ts
            active = fusion if fusion is not None else sflp
            source = None
            if active is fusion and fusion is not None:
                source = "fusion"
            elif active is sflp and sflp is not None:
                source = "sflp"
            punch = self._last_punch
            punch_ts = self._last_punch_ts
            mag = (
                None
                if self._latest_mag is None
                else np.array(self._latest_mag, copy=True)
            )
            mag_ts = self._mag_ts
            flex_value = self._flex_value
            flex_raw = self._flex_raw_median
            flex_midi = self._flex_midi
            flex_ts = self._flex_ts
        return (
            fusion,
            sflp,
            active,
            source,
            position,
            ts,
            punch,
            punch_ts,
            mag,
            mag_ts,
            flex_value,
            flex_raw,
            flex_midi,
            flex_ts,
        )


# ----------------------------- Dispatcher and buffer --------------------------


class LineDispatcher:
    def __init__(
        self,
        telemetry: TelemetryState,
        cli_queue: "queue.Queue[str]",
        monitor_queue: "queue.Queue[str]",
        log_filter: _LogLineFilter,
    ):
        self._telemetry = telemetry
        self._cli_queue = cli_queue
        self._monitor_queue = monitor_queue
        self._log_filter = log_filter
        self._pending_cli: list[str] = []

    def handle_line(self, line: str) -> None:
        stripped = line.rstrip("\r\n")
        if not stripped:
            return
        self._telemetry.ingest_line(stripped)
        segments = self._split_line(stripped)
        self._emit_segments(segments)
        self._maybe_flush_cli(segments, force=False)

    def flush_fragment(self, fragment: str) -> None:
        frag = fragment.rstrip("\r\n")
        if not frag:
            return
        segments = self._split_line(frag)
        self._emit_segments(segments)
        self._maybe_flush_cli(segments, force=True)

    def _emit_segments(self, segments: list[tuple[str, str]]) -> None:
        for text, kind in segments:
            if not text:
                continue
            if kind == "log":
                plain_log = _strip_ansi_prefix(text)
                match = LOG_LINE_RE.match(plain_log)
                if match is None:
                    self._pending_cli.append(text)
                    continue
                tag = match.group("tag").strip().upper()
                if tag not in SUPPRESSED_MONITOR_TAGS:
                    self._monitor_queue.put(text)
                if self._log_filter.allows(match):
                    self._cli_queue.put(text + "\n")
            else:
                self._pending_cli.append(text)

    def _maybe_flush_cli(self, segments: list[tuple[str, str]], force: bool) -> None:
        if not self._pending_cli:
            return
        last_kind = segments[-1][1] if segments else None
        should_flush = force or last_kind == "cli"
        if not should_flush:
            return
        payload = "".join(self._pending_cli)
        if not force:
            payload += "\n"
        self._cli_queue.put(payload)
        self._pending_cli.clear()

    def _split_line(self, text: str) -> list[tuple[str, str]]:
        segments: list[tuple[str, str]] = []
        if not text:
            return segments
        ansi_match = ANSI_PREFIX_RE.match(text)
        prefix_len = ansi_match.end() if ansi_match else 0
        if prefix_len:
            segments.append((text[:prefix_len], "cli"))
        plain = text[prefix_len:]
        cursor = 0
        length = len(plain)
        while cursor < length:
            indices = [plain.find(prefix, cursor) for prefix in LOG_PREFIXES]
            indices = [idx for idx in indices if idx != -1]
            if not indices:
                remainder = plain[cursor:]
                if remainder:
                    segments.append(
                        (text[prefix_len + cursor : prefix_len + length], "cli")
                    )
                break
            idx = min(indices)
            candidate = plain[idx:]
            match = LOG_LINE_RE.match(candidate)
            if match is None:
                cursor = idx + 1
                continue
            if idx > cursor:
                cli_slice = text[prefix_len + cursor : prefix_len + idx]
                if cli_slice:
                    segments.append((cli_slice, "cli"))
            log_len = match.end()
            if log_len <= 0:
                break
            log_slice = text[prefix_len + idx : prefix_len + idx + log_len]
            segments.append((log_slice, "log"))
            cursor = idx + log_len
        return segments


class LineBuffer:
    def __init__(
        self, handle_line: Callable[[str], None], flush_fragment: Callable[[str], None]
    ):
        self._buffer = ""
        self._handle_line = handle_line
        self._flush_fragment = flush_fragment

    @staticmethod
    def _next_newline_index(buffer: str) -> Optional[int]:
        if not buffer:
            return None
        positions = [idx for idx in (buffer.find("\n"), buffer.find("\r")) if idx != -1]
        if not positions:
            return None
        return min(positions)

    @staticmethod
    def _consume_newline(buffer: str, newline_index: int) -> int:
        consume = newline_index + 1
        if (
            buffer[newline_index] == "\r"
            and consume < len(buffer)
            and buffer[consume] == "\n"
        ):
            consume += 1
        return consume

    def feed(self, chunk: str) -> None:
        if not chunk:
            return
        self._buffer += chunk
        while True:
            newline_idx = self._next_newline_index(self._buffer)
            if newline_idx is None:
                break
            consume = self._consume_newline(self._buffer, newline_idx)
            line = self._buffer[:newline_idx]
            self._buffer = self._buffer[consume:]
            self._handle_line(line)
        if self._buffer and len(self._buffer) > 256:
            self._flush_fragment(self._buffer)
            self._buffer = ""

    def flush(self) -> None:
        if self._buffer:
            self._flush_fragment(self._buffer)
            self._buffer = ""


# ----------------------------- Serial and BLE clients -------------------------


class SerialTelemetryClient(threading.Thread):
    def __init__(
        self,
        port: str,
        baud: int,
        dispatcher: LineDispatcher,
        status_queue: "queue.Queue[str]",
    ):
        super().__init__(daemon=True)
        self._port = port
        self._baud = baud
        self._dispatcher = dispatcher
        self._status_queue = status_queue
        self._stop = threading.Event()
        self._serial = None
        self._buffer = LineBuffer(
            self._dispatcher.handle_line, self._dispatcher.flush_fragment
        )
        try:
            import serial as serial_mod  # type: ignore

            if not hasattr(serial_mod, "Serial"):
                raise ImportError(
                    "Imported 'serial' module is not PySerial. Fix with:\n"
                    "  pip uninstall -y serial\n  pip install pyserial"
                )
            self._serial_mod = serial_mod
        except Exception as exc:
            raise RuntimeError("pyserial is required for UART mode") from exc

    def stop(self) -> None:
        self._stop.set()
        if self._serial and getattr(self._serial, "cancel_read", None):
            try:
                self._serial.cancel_read()
            except Exception:
                pass
        if self.is_alive():
            self.join(timeout=2.0)

    def send_text(self, text: str) -> None:
        if not text or not self._serial or not self._serial.is_open:
            return
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.endswith("\n"):
            normalized += "\n"
        payload = normalized.replace("\n", "\r\n")
        try:
            self._serial.write(payload.encode("utf-8"))
        except Exception:
            pass

    def run(self) -> None:  # pragma: no cover
        import serial.tools.list_ports

        connected = False
        reconnect_attempt = 0

        while not self._stop.is_set():
            # Try to connect/reconnect
            if not connected:
                try:
                    # Check if port exists before attempting connection
                    available_ports = [p.device for p in serial.tools.list_ports.comports()]
                    if self._port not in available_ports:
                        if reconnect_attempt == 0:
                            self._status_queue.put(f"Serial waiting for device on {self._port}...")
                        reconnect_attempt += 1
                        time.sleep(1.5)
                        continue

                    self._serial = self._serial_mod.Serial(self._port, self._baud, timeout=1)
                    connected = True
                    reconnect_attempt = 0
                    self._status_queue.put(f"Serial connected: {self._port} @ {self._baud}")
                except Exception as exc:
                    if reconnect_attempt == 0:
                        self._status_queue.put(f"Serial connection failed: {exc}, retrying...")
                    reconnect_attempt += 1
                    time.sleep(1.5)
                    continue

            # Read data while connected
            try:
                raw = self._serial.readline()
                if not raw:
                    continue
                text = raw.decode(errors="ignore")
                self._buffer.feed(text)
            except Exception as exc:
                # Connection lost - close and retry
                self._status_queue.put(f"Serial disconnected, reconnecting: {exc}")
                try:
                    if self._serial:
                        self._serial.close()
                except Exception:  # pragma: no cover
                    # Ignore close errors to keep shutdown robust
                    pass
                self._serial = None
                connected = False
                reconnect_attempt = 0
                continue

        # Clean shutdown
        try:
            self._buffer.flush()
        finally:
            if self._serial:
                try:
                    self._serial.close()
                except Exception:  # pragma: no cover
                    # Ignore close errors to keep shutdown robust
                    pass
            self._status_queue.put("Serial disconnected")


class BleTelemetryClient:
    def __init__(
        self,
        name_hint: Optional[str],
        address: Optional[str],
        scan_time: float,
        timeout: float,
        dispatcher: LineDispatcher,
        status_queue: "queue.Queue[str]",
    ):
        self._name_hint = name_hint
        self._address = address
        self._scan_time = scan_time
        self._timeout = timeout
        self._dispatcher = dispatcher
        self._status_queue = status_queue
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._commands: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._client = None
        self._buffer = LineBuffer(
            self._dispatcher.handle_line, self._dispatcher.flush_fragment
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        def _stop_loop() -> None:
            self._stop_event.set()
            self._commands.put_nowait(None)

        try:
            self._loop.call_soon_threadsafe(_stop_loop)
        except RuntimeError:
            return
        if self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def send_text(self, text: str) -> None:
        if not text:
            return
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.endswith("\n"):
            normalized += "\n"
        encoded = normalized.replace("\n", "\r\n").encode("utf-8")

        def _enqueue() -> None:
            if not self._commands.full():
                self._commands.put_nowait(encoded)

        try:
            self._loop.call_soon_threadsafe(_enqueue)
        except RuntimeError:
            pass

    def _thread_main(self) -> None:  # pragma: no cover
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run())
        finally:
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

    async def _run(self) -> None:
        try:
            from bleak import BleakClient, BleakScanner
        except Exception as exc:
            self._status_queue.put(f"BLE unavailable: {exc}")
            return

        async def _resolve_target() -> Optional[str]:
            if self._address:
                self._status_queue.put(f"BLE: connecting to {self._address} ...")
                return self._address
            hint = (self._name_hint or BLE_DEFAULT_NAME_HINT).lower()
            self._status_queue.put(
                f"BLE: scanning for devices matching '{hint}' ({self._scan_time:.1f}s timeout)"
            )

            def _matches(device, adv_data):
                name = (device.name or "").lower()
                adv_name = (adv_data.local_name or "").lower()
                return hint in name or hint in adv_name

            device = await BleakScanner.find_device_by_filter(
                _matches, timeout=self._scan_time
            )
            if not device:
                return None
            self._status_queue.put(
                f"BLE: found {device.name or 'Unnamed'} ({device.address}). Connecting..."
            )
            return device.address

        reconnect_attempt = 0
        while not self._stop_event.is_set():
            target = await _resolve_target()
            if not target:
                if reconnect_attempt == 0:
                    self._status_queue.put(
                        "BLE: device not found, retrying scan..."
                    )
                reconnect_attempt += 1
                await asyncio.sleep(2.0)
                continue

            try:
                # Set up disconnection callback before creating client
                disconnected_event = asyncio.Event()
                def _on_disconnect(client):
                    disconnected_event.set()

                async with BleakClient(target, timeout=self._timeout, disconnected_callback=_on_disconnect) as client:
                    self._client = client

                    await client.start_notify(NUS_TX_CHAR_UUID, self._handle_notify)
                    self._status_queue.put("BLE connected. Receiving notifications...")
                    reconnect_attempt = 0

                    while not self._stop_event.is_set() and not disconnected_event.is_set():
                        try:
                            payload = await asyncio.wait_for(
                                self._commands.get(), timeout=0.1
                            )
                        except asyncio.TimeoutError:
                            continue
                        if payload is None:
                            break
                        await _write_nus(client, payload)

                    # Check if we exited due to disconnection
                    if disconnected_event.is_set():
                        self._status_queue.put("BLE disconnected, reconnecting...")
                        reconnect_attempt += 1
                        await asyncio.sleep(2.0)
                        continue

                    await client.stop_notify(NUS_TX_CHAR_UUID)
                    break  # Clean exit requested
            except Exception as exc:
                error_msg = str(exc)
                if reconnect_attempt == 0:
                    self._status_queue.put(f"BLE connection error: {error_msg}, reconnecting...")
                else:
                    # Show error periodically (every 5 attempts)
                    if reconnect_attempt % 5 == 0:
                        self._status_queue.put(f"BLE reconnect attempt {reconnect_attempt} failed: {error_msg}")
                reconnect_attempt += 1
                await asyncio.sleep(2.0)
                continue

        self._buffer.flush()
        self._status_queue.put("BLE disconnected")

    def _handle_notify(self, _characteristic: object, data: bytearray) -> None:
        try:
            chunk = data.decode(errors="ignore")
        except Exception:
            chunk = data.decode("utf-8", errors="ignore")
        self._buffer.feed(chunk)


async def _write_nus(client, payload: bytes) -> None:
    if not payload:
        return
    mtu = getattr(client, "mtu_size", None)
    if mtu is None:
        chunk_size = DEFAULT_WRITE_CHUNK
    else:
        chunk_size = max(DEFAULT_WRITE_CHUNK, int(mtu) - 3)
    for offset in range(0, len(payload), chunk_size):
        chunk = payload[offset : offset + chunk_size]
        await client.write_gatt_char(NUS_RX_CHAR_UUID, chunk, response=False)
        if len(payload) > chunk_size:
            await asyncio.sleep(0)


# ----------------------------- Qt UI ------------------------------------------

from PySide6 import QtCore, QtGui, QtWidgets

# Use Matplotlib QtAgg canvas
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Circle

if TYPE_CHECKING:
    from mpl_toolkits.mplot3d.axes3d import Axes3D
    from mpl_toolkits.mplot3d.art3d import Line3D, Path3DCollection
    from matplotlib.axes import Axes
    from matplotlib.lines import Line2D


class PillSplitterHandle(QtWidgets.QSplitterHandle):
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        pill_width = 30
        pill_height = 3

        if self.orientation() == QtCore.Qt.Orientation.Horizontal:
            # Vertical pill (for horizontal splitter)
            center_x = rect.width() / 2
            pill_rect = QtCore.QRectF(center_x - pill_height/2, rect.height() / 2 - pill_width / 2, pill_height, pill_width)
        else:
            # Horizontal pill (for vertical splitter)
            center_y = rect.height() / 2
            pill_rect = QtCore.QRectF(rect.width() / 2 - pill_width / 2, center_y - pill_height / 2, pill_width, pill_height)

        painter.setBrush(QtGui.QColor("#ccc"))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(pill_rect, 2, 2)


class PillSplitter(QtWidgets.QSplitter):
    def createHandle(self):
        return PillSplitterHandle(self.orientation(), self)


class DashboardWindow(QtWidgets.QMainWindow):
    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self.args = args

        allowed_tags = None
        if args.log_tags:
            allowed_tags = {
                token
                for token in (t.strip() for t in args.log_tags.split(","))
                if token
            }

        self.telemetry = TelemetryState()
        self.cli_queue: "queue.Queue[str]" = queue.Queue()
        self.monitor_queue: "queue.Queue[str]" = queue.Queue()
        self.status_queue: "queue.Queue[str]" = queue.Queue()
        self.log_filter = _LogLineFilter(args.show_logs, allowed_tags)
        self.dispatcher = LineDispatcher(
            self.telemetry, self.cli_queue, self.monitor_queue, self.log_filter
        )

        # Transport state
        self.ble_preferred = not self.args.serial_only
        self.serial_allowed = not self.args.ble_only
        self.transport_desc = (
            "BLE (searching)" if self.ble_preferred else "Serial (connecting)"
        )
        self.info_battery = "--"
        self.info_voltage: Optional[str] = None
        self.info_rssi = "--"
        self.orientation_source = "Waiting"
        self.punch_display_duration = 2.0
        self.punch_velocity_full_scale = 6.0
        self.flex_meter_full_scale = 127.0
        self.flex_meter_stale_timeout = 2.5
        self.flex_bar = None
        self.flex_value_label = None

        base_vec = np.array(args.vector, dtype=float)
        if np.linalg.norm(base_vec) == 0:
            base_vec = np.array([0.0, 0.0, 1.0])
        self.base_vec = base_vec / np.linalg.norm(base_vec)

        self._build_ui()
        self._load_splitter_state()

        # Plot state
        self.position_trail: deque[np.ndarray] = deque(maxlen=300)
        self.last_position_ts = 0.0
        self._last_trail_radius = 1.5
        self.orientation_radius = 1.0
        self.compass_full_scale = 60.0
        self.compass_max_radius = 0.85

        # Start transport
        self.client = self._start_transport()

        # Timers
        self.queue_timer = QtCore.QTimer(self)
        self.queue_timer.setInterval(25)
        self.queue_timer.timeout.connect(self._poll_queues)
        self.queue_timer.start()

        self.plot_timer = QtCore.QTimer(self)
        self.plot_timer.setInterval(33)  # ~30 Hz
        self.plot_timer.timeout.connect(self._update_plot)
        self.plot_timer.start()

        # Ctrl+C handler to close cleanly
        signal.signal(signal.SIGINT, lambda *_: self.close())

    # ------------------------- UI layout --------------------------------------

    def _create_monospace_font(self) -> QtGui.QFont:
        """Create a monospaced font with consistent styling."""
        font = QtGui.QFont()
        font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
        font.setFamily(
            QtGui.QFontDatabase.systemFont(
                QtGui.QFontDatabase.SystemFont.FixedFont
            ).family()
        )
        font.setPointSize(MONOSPACE_FONT_SIZE)
        return font

    def _build_ui(self) -> None:
        self.setWindowTitle("G-Love Dashboard (Qt)")
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)

        root_split = PillSplitter(QtCore.Qt.Orientation.Horizontal, central)
        root_layout = QtWidgets.QHBoxLayout(central)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.addWidget(root_split)

        # Left: Matplotlib figure
        self.figure = Figure(figsize=(10, 8))
        gs = self.figure.add_gridspec(
            3,
            2,
            height_ratios=[1.6, 1.0, 0.45],
            width_ratios=[1.0, 0.85],
            hspace=0.32,
            wspace=0.32,
        )
        self.ax_orientation = cast(
            "Axes3D", self.figure.add_subplot(gs[0, :], projection="3d")
        )
        self.ax_position = cast(
            "Axes3D", self.figure.add_subplot(gs[1, 0], projection="3d")
        )
        self.ax_compass = self.figure.add_subplot(gs[1, 1])
        self.ax_flex = self.figure.add_subplot(gs[2, :])

        self.canvas = FigureCanvas(self.figure)
        root_split.addWidget(self.canvas)

        # Right: Sidebar with CLI and Monitor
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)

        self.status_label = QtWidgets.QLabel("Connecting...")
        self.info_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        self.info_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)
        right_layout.addWidget(self.info_label)

        inner_split = PillSplitter(QtCore.Qt.Orientation.Vertical)
        right_layout.addWidget(inner_split, 1)

        # CLI container
        cli_container = QtWidgets.QWidget()
        cli_layout = QtWidgets.QVBoxLayout(cli_container)
        cli_layout.setContentsMargins(0, 0, 0, 0)
        cli_layout.setSpacing(0)

        cli_header = QtWidgets.QHBoxLayout()
        cli_title = QtWidgets.QLabel("CLI Console")
        self.cli_clear_btn = QtWidgets.QPushButton("Clear")
        self.cli_clear_btn.clicked.connect(self._clear_cli_console)
        cli_header.addWidget(cli_title, 1)
        cli_header.addWidget(self.cli_clear_btn)
        cli_layout.addLayout(cli_header)

        self.cli_text = QtWidgets.QPlainTextEdit()
        self.cli_text.setReadOnly(True)
        self.cli_text.setLineWrapMode(
            QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap
        )
        self.cli_text.document().setMaximumBlockCount(5000)
        # Set monospaced font for CLI console
        self.cli_text.setFont(self._create_monospace_font())
        cli_layout.addWidget(self.cli_text, 1)

        self.cli_input = QtWidgets.QPlainTextEdit()
        self.cli_input.setFixedHeight(90)
        self.cli_input.installEventFilter(self)
        # Set monospaced font for command input
        self.cli_input.setFont(self._create_monospace_font())

        cmd_input_header = QtWidgets.QHBoxLayout()
        cmd_input_title = QtWidgets.QLabel("Command Input")
        self.cmd_input_clear_btn = QtWidgets.QPushButton("Clear")
        self.cmd_input_clear_btn.clicked.connect(self._clear_command_input)
        cmd_input_header.addWidget(cmd_input_title, 1)
        cmd_input_header.addWidget(self.cmd_input_clear_btn)
        cli_layout.addLayout(cmd_input_header)
        cli_layout.addWidget(self.cli_input)

        # Monitor container
        mon_container = QtWidgets.QWidget()
        mon_layout = QtWidgets.QVBoxLayout(mon_container)
        mon_layout.setContentsMargins(0, 0, 0, 0)
        mon_layout.setSpacing(0)

        mon_header = QtWidgets.QHBoxLayout()
        mon_title = QtWidgets.QLabel("Monitor Logs")
        self.monitor_clear_btn = QtWidgets.QPushButton("Clear")
        self.monitor_clear_btn.clicked.connect(self._clear_monitor_logs)
        mon_header.addWidget(mon_title, 1)
        mon_header.addWidget(self.monitor_clear_btn)
        mon_layout.addLayout(mon_header)
        self.monitor_text = QtWidgets.QPlainTextEdit()
        self.monitor_text.setReadOnly(True)
        self.monitor_text.setLineWrapMode(
            QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap
        )
        self.monitor_text.document().setMaximumBlockCount(5000)
        # Set monospaced font for monitor logs
        self.monitor_text.setFont(self._create_monospace_font())
        mon_layout.addWidget(self.monitor_text, 1)

        inner_split.addWidget(cli_container)
        inner_split.addWidget(mon_container)
        inner_split.setStretchFactor(0, 3)
        inner_split.setStretchFactor(1, 2)

        root_split.addWidget(right_panel)
        root_split.setStretchFactor(0, 2)
        root_split.setStretchFactor(1, 3)

        # Axes setup
        self._setup_axes(
            self.ax_orientation,
            f"Active orientation ({self.orientation_source})",
            hide_cartesian=True,
        )
        self._setup_axes(self.ax_position, "Position estimate (m)")
        self._setup_compass_axes(self.ax_compass)
        self._setup_flex_axes(self.ax_flex)
        self._refresh_orientation_title()
        self._add_unit_sphere(self.ax_orientation, 1.0)
        margin = 0.03
        span = 1.0 + margin
        self.ax_orientation.set_autoscale_on(False)
        self.ax_orientation.set_xlim([-span, span])
        self.ax_orientation.set_ylim([-span, span])
        self.ax_orientation.set_zlim([-span, span])
        self.ax_position.set_xlim([-1.5, 1.5])
        self.ax_position.set_ylim([-1.5, 1.5])
        self.ax_position.set_zlim([-1.5, 1.5])

        # Orientation primitives
        pointer_origin = self.base_vec.copy()
        self.active_pointer_line = cast(
            "Line3D",
            self.ax_orientation.plot(
                [0, pointer_origin[0]],
                [0, pointer_origin[1]],
                [0, pointer_origin[2]],
                color="#1E90FF",
                linewidth=3,
            )[0],
        )
        self.punch_line = cast(
            "Line3D",
            self.ax_orientation.plot(
                [0.0, 0.0],
                [0.0, 0.0],
                [0.0, 0.0],
                color="#FF1493",
                linewidth=2.5,
                alpha=0.0,
            )[0],
        )
        self.punch_line.set_visible(False)
        self.active_marker = cast(
            "Path3DCollection",
            cast(Any, self.ax_orientation).scatter(
                [pointer_origin[0]],
                [pointer_origin[1]],
                zs=[pointer_origin[2]],
                s=80,
                color="#1E90FF",
            ),
        )
        self.active_angles_label = self.ax_orientation.text2D(
            0.02,
            0.9,
            "Roll: +0.0 deg, Pitch: +0.0 deg, Yaw: +0.0 deg",
            transform=self.ax_orientation.transAxes,
        )

        # Position primitives
        self.position_point = cast(
            "Line3D",
            self.ax_position.plot(
                [0], [0], [0], marker="o", markersize=9, color="orange"
            )[0],
        )
        self.trail_line = cast(
            "Line3D",
            self.ax_position.plot([], [], [], color="orange", linewidth=1.2, alpha=0.6)[
                0
            ],
        )
        self.position_label = self.ax_position.text2D(
            0.02, 0.95, "Pos: (0.00, 0.00, 0.00)", transform=self.ax_position.transAxes
        )

        # Status bar content
        self._refresh_info_bar()

        # Intro text
        self._init_cli_console()

    # Persist/restore splitter widths
    def _load_splitter_state(self) -> None:
        try:
            data = json.loads(LAYOUT_STATE_FILE.read_text(encoding="utf-8"))
            geo = data.get("geometry")
            if isinstance(geo, str):
                restored_bytes = base64.b64decode(geo.encode("ascii"))
                if restored_bytes:
                    self.restoreGeometry(QtCore.QByteArray(restored_bytes))
        except Exception:
            pass

    def _save_splitter_state(self) -> None:
        try:
            geometry_bytes = bytes(self.saveGeometry().data())
            geometry = base64.b64encode(geometry_bytes).decode("ascii")
            payload = {"geometry": geometry}
            LAYOUT_STATE_FILE.write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            pass

    # ------------------------- CLI, info, helpers -----------------------------

    def _init_cli_console(self) -> None:
        self.cli_text.setPlainText(
            "CLI ready. Press Enter to send; Shift+Enter inserts a newline.\n"
        )
        self.cli_input.setFocus()

    def _clear_cli_console(self) -> None:
        self.cli_text.clear()

    def _clear_monitor_logs(self) -> None:
        self.monitor_text.clear()

    def _clear_command_input(self) -> None:
        self.cli_input.clear()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self.cli_input and event.type() == QtCore.QEvent.Type.KeyPress:
            key = cast(QtGui.QKeyEvent, event).key()
            modifiers = cast(QtGui.QKeyEvent, event).modifiers()
            if key == QtCore.Qt.Key.Key_Return or key == QtCore.Qt.Key.Key_Enter:
                if modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier:
                    return False  # allow newline
                self._submit_cli_input()
                return True
            elif key == QtCore.Qt.Key.Key_Up:
                self._hist_back()
                return True
            elif key == QtCore.Qt.Key.Key_Down:
                self._hist_forward()
                return True
        return super().eventFilter(obj, event)

    def _submit_cli_input(self) -> None:
        raw = self.cli_input.toPlainText().strip()
        if not raw:
            self.cli_input.clear()
            return
        if raw.lower() == "clear":
            self.cli_history.append(raw)
            self.cli_history_index = None
            self.cli_input.clear()
            self._clear_cli_console()
            return
        normalized = self._prepare_cli_command(raw)
        if not normalized:
            self.cli_input.clear()
            return
        self.cli_history.append(normalized)
        self.cli_history_index = None
        self.cli_input.clear()
        self._append_cli_output(self._format_command_for_display(normalized))
        self._emit_command(normalized)

    def _format_command_for_display(self, command: str) -> str:
        lines = command.splitlines() or [command]
        formatted = ["> " + lines[0]]
        formatted.extend("  " + line for line in lines[1:])
        return "\n".join(formatted)

    def _append_cli_output(self, text: str) -> None:
        if not text:
            return
        # JSON pretty-minifier while appending
        payload = text
        # Simple pass-through; pretty-JSON is handled in batch appender below
        self.cli_text.moveCursor(QtGui.QTextCursor.MoveOperation.End)
        self.cli_text.insertPlainText(
            payload + ("\n" if not payload.endswith("\n") else "")
        )
        self.cli_text.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _append_cli_output_batch(self, lines: list[str]) -> None:
        if not lines:
            return
        payload = "".join(lines)
        if not payload:
            return
        # Convert embedded JSON objects into pretty form
        out = []
        buf = ""
        in_json = False
        depth = 0
        i = 0
        while i < len(payload):
            ch = payload[i]
            if not in_json and ch == "{":
                in_json = True
                depth = 1
                buf = ch
            elif in_json:
                buf += ch
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(buf)
                            out.append(json.dumps(parsed, indent=2) + "\n")
                        except Exception:
                            out.append(buf.replace("\t", "  "))
                        buf = ""
                        in_json = False
            else:
                out.append(ch)
            i += 1
        if buf:
            out.append(buf)
        text = "".join(out).replace("\t", "  ")
        self.cli_text.moveCursor(QtGui.QTextCursor.MoveOperation.End)
        self.cli_text.insertPlainText(text)
        self.cli_text.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _append_monitor_batch(self, lines: list[str]) -> None:
        if not lines:
            return
        filtered = []
        for raw in lines:
            clean = raw.rstrip("\r\n")
            if not clean:
                continue
            plain = _strip_ansi_prefix(clean)
            match = LOG_LINE_RE.match(plain)
            if match and match.group("tag").strip().upper() in ("BATT", "RSSI"):
                continue
            filtered.append(clean + "\n")
        if not filtered:
            return
        self.monitor_text.moveCursor(QtGui.QTextCursor.MoveOperation.End)
        self.monitor_text.insertPlainText("".join(filtered))
        self.monitor_text.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _update_info_from_line(self, text: str) -> None:
        plain = _strip_ansi_prefix(text)
        updated = False
        batt_match = BATT_RE.search(plain)
        if batt_match:
            percent_raw = batt_match.group(1)
            voltage_raw = batt_match.group(2)
            try:
                percent_val = float(percent_raw)
                self.info_battery = f"{percent_val:.1f}".rstrip("0").rstrip(".")
            except ValueError:
                self.info_battery = percent_raw.strip()
            try:
                volt_val = float(voltage_raw)
                self.info_voltage = f"{volt_val:.2f}".rstrip("0").rstrip(".")
            except ValueError:
                self.info_voltage = voltage_raw.strip()
            updated = True
        rssi_match = RSSI_RE.search(plain)
        if rssi_match:
            self.info_rssi = rssi_match.group(1).strip()
            updated = True
        if updated:
            self._refresh_info_bar()

    def _refresh_info_bar(self) -> None:
        parts = [f"Transport: {self.transport_desc}"]
        if self.info_battery != "--":
            battery_segment = f"Battery: {self.info_battery}%"
            if self.info_voltage:
                battery_segment += f" ({self.info_voltage}V)"
            parts.append(battery_segment)
        else:
            parts.append("Battery: --")
        parts.append(
            f"RSSI: {self.info_rssi} dBm" if self.info_rssi != "--" else "RSSI: --"
        )
        self.info_label.setText(" | ".join(parts))
        self._refresh_orientation_title()

    def _refresh_orientation_title(self) -> None:
        title = f"Active orientation ({self.orientation_source})"
        if self.ax_orientation.get_title() != title:
            self.ax_orientation.set_title(title)
            self.canvas.draw_idle()

    def _hist_back(self) -> None:
        if not hasattr(self, "cli_history") or not self.cli_history:
            return
        if self.cli_history_index is None:
            self.cli_history_index = len(self.cli_history) - 1
        else:
            self.cli_history_index = max(0, self.cli_history_index - 1)
        self.cli_input.setPlainText(self.cli_history[self.cli_history_index])
        self.cli_input.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _hist_forward(self) -> None:
        if not hasattr(self, "cli_history") or not self.cli_history:
            return
        if self.cli_history_index is None:
            return
        if self.cli_history_index >= len(self.cli_history) - 1:
            self.cli_history_index = None
            self.cli_input.clear()
        else:
            self.cli_history_index += 1
            self.cli_input.setPlainText(self.cli_history[self.cli_history_index])
            self.cli_input.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    cli_history: list[str] = []
    cli_history_index: Optional[int] = None

    def _prepare_cli_command(self, raw: str) -> str:
        text = raw.strip()
        if not text:
            return ""
        if "\n" not in text:
            return text
        stripped = text.strip()
        if stripped and stripped[0] in "{[":
            try:
                parsed = json.loads(stripped)
                return json.dumps(parsed, separators=(",", ":"))
            except Exception:
                pass
        brace_indices = [
            idx for idx in (stripped.find("{"), stripped.find("[")) if idx != -1
        ]
        if brace_indices:
            start = min(brace_indices)
            prefix = stripped[:start].strip()
            json_body = stripped[start:].strip()
            try:
                parsed = json.loads(json_body)
                minified = json.dumps(parsed, separators=(",", ":"))
                return f"{prefix} {minified}".strip()
            except Exception:
                pass
        collapsed = " ".join(
            segment.strip() for segment in stripped.splitlines() if segment.strip()
        )
        return collapsed or stripped

    def _setup_axes(self, ax, title: str, hide_cartesian: bool = False) -> None:
        ax.set_title(title)
        ax.set_xlim([-1.1, 1.1])
        ax.set_ylim([-1.1, 1.1])
        ax.set_zlim([-1.1, 1.1])
        try:
            ax.set_box_aspect([1, 1, 1])
        except Exception:
            pass
        if hide_cartesian:
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_zticks([])
            ax.grid(False)
            try:
                ax.set_axis_off()
            except Exception:
                pass
        else:
            ax.set_xlabel("X")
            ax.set_ylabel("Y")
            ax.set_zlabel("Z")

    def _setup_compass_axes(self, ax) -> None:
        ax.set_title("Compass heading (µT)", pad=24)
        ax.set_xlim([-1.1, 1.1])
        ax.set_ylim([-1.1, 1.1])
        ax.set_aspect("equal", adjustable="box")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.grid(False)
        circle = Circle(
            (0.0, 0.0), 1.0, fill=False, linewidth=0.8, color="#B0B0B0", alpha=0.6
        )
        ax.add_patch(circle)
        ax.axhline(0.0, color="#D0D0D0", linewidth=0.6)
        ax.axvline(0.0, color="#D0D0D0", linewidth=0.6)
        ax.text(0.0, 1.05, "N", ha="center", va="center", fontsize=9)
        ax.text(0.0, -1.05, "S", ha="center", va="center", fontsize=9)
        ax.text(1.05, 0.0, "E", ha="center", va="center", fontsize=9)
        ax.text(-1.05, 0.0, "W", ha="center", va="center", fontsize=9)
        self.compass_line = ax.plot(
            [0.0, 0.0],
            [0.0, 0.0],
            color="#1E90FF",
            linewidth=2.4,
            solid_capstyle="round",
        )[0]
        self.compass_marker = ax.plot(
            [0.0], [0.0], marker="o", color="#1E90FF", markersize=6
        )[0]
        self.compass_line.set_visible(False)
        self.compass_marker.set_visible(False)
        self.compass_heading_label = ax.text(
            0.5, -0.02, "Heading: --", transform=ax.transAxes, ha="center", va="top"
        )
        self.compass_field_label = ax.text(
            0.5, -0.16, "|B|: -- µT", transform=ax.transAxes, ha="center", va="top"
        )

    def _setup_flex_axes(self, ax) -> None:
        ax.set_title("Flex level (MIDI)")
        ax.set_xlim([0.0, self.flex_meter_full_scale])
        ax.set_ylim([0.0, 1.0])
        ax.set_yticks([])
        ax.set_xlabel("MIDI value")
        ax.set_facecolor("#F7F7F7")
        for spine in ax.spines.values():
            spine.set_visible(False)
        tick_positions = [0, 32, 64, 96, int(self.flex_meter_full_scale)]
        ax.set_xticks(tick_positions)
        ax.tick_params(axis="x", labelsize=9)
        bar_color = "#1E90FF"
        self.flex_bar = ax.barh(
            0.5,
            0.0,
            height=0.6,
            align="center",
            color=bar_color,
            alpha=0.2,
        )[0]
        self.flex_value_label = ax.text(
            0.02,
            0.5,
            "MIDI: --  Raw: --  Index: --",
            transform=ax.transAxes,
            ha="left",
            va="center",
            fontsize=10,
            color="#606060",
        )

    def _add_unit_sphere(self, ax, radius: float) -> None:
        phi = np.linspace(0.0, np.pi, 20)
        theta = np.linspace(0.0, 2.0 * np.pi, 40)
        x = radius * np.outer(np.sin(phi), np.cos(theta))
        y = radius * np.outer(np.sin(phi), np.sin(theta))
        z = radius * np.outer(np.cos(phi), np.ones_like(theta))
        ax.plot_wireframe(x, y, z, color="#B0B0B0", linewidth=0.4, alpha=0.35)

    # ------------------------- Transport start/update -------------------------

    def _attempt_ble_start(self) -> Optional[BleTelemetryClient]:
        target, logs = _resolve_ble_target_sync(
            self.args.ble_name, self.args.ble_address, self.args.ble_scan_time
        )
        for msg in logs:
            self.status_queue.put(msg)
        if target is None:
            return None
        client = BleTelemetryClient(
            name_hint=self.args.ble_name,
            address=target,
            scan_time=self.args.ble_scan_time,
            timeout=self.args.ble_timeout,
            dispatcher=self.dispatcher,
            status_queue=self.status_queue,
        )
        client.start()
        self.transport_desc = "BLE (connecting)"
        self._refresh_info_bar()
        return client

    def _emit_command(self, command: str) -> None:
        if not command:
            return
        client = getattr(self, "client", None)
        if client is None or not hasattr(client, "send_text"):
            self.status_queue.put("Transport unavailable; command skipped.")
            return
        try:
            client.send_text(command)
        except Exception as exc:  # pragma: no cover - best effort logging
            self.status_queue.put(f"Command send failed: {exc}")

    def _start_transport(self):
        if self.ble_preferred:
            client = self._attempt_ble_start()
            if client is not None:
                return client
            if not self.serial_allowed:
                QtWidgets.QMessageBox.critical(
                    self,
                    "BLE Connection Failed",
                    "No BLE device discovered and BLE-only mode was requested.",
                )
                QtCore.QTimer.singleShot(0, self.close)
                raise SystemExit(1)
            self.status_queue.put("BLE: falling back to serial.")
            self.transport_desc = "Serial (connecting)"
            self._refresh_info_bar()
        else:
            self.transport_desc = "Serial (connecting)"
            self._refresh_info_bar()

        port = self.args.port or find_default_port()
        if not port:
            QtWidgets.QMessageBox.critical(
                self,
                "Serial Port Not Found",
                "Could not auto-detect a serial port under /dev/tty.* or /dev/cu.*. Use -p to specify one.",
            )
            QtCore.QTimer.singleShot(0, self.close)
            raise SystemExit(1)
        try:
            client = SerialTelemetryClient(
                port=port,
                baud=self.args.baud,
                dispatcher=self.dispatcher,
                status_queue=self.status_queue,
            )
        except RuntimeError as exc:
            QtWidgets.QMessageBox.critical(self, "Serial Dependency Missing", str(exc))
            QtCore.QTimer.singleShot(0, self.close)
            raise SystemExit(1)
        client.start()
        return client

    def _update_transport_from_status(self, status: str) -> None:
        normalized = status.strip()
        lower = normalized.lower()
        if lower.startswith("serial connected:"):
            self.transport_desc = normalized.replace(
                "Serial connected:", "Serial"
            ).strip()
        elif "serial" in lower and ("disconnected" in lower or "failed" in lower):
            self.transport_desc = "Serial (disconnected)"
        elif "serial" in lower and "waiting" in lower:
            self.transport_desc = "Serial (reconnecting)"
        elif lower.startswith("ble connected"):
            self.transport_desc = "BLE (connected)"
        elif "ble" in lower and "disconnected" in lower:
            self.transport_desc = "BLE (reconnecting)"
        elif lower.startswith("ble: found"):
            self.transport_desc = normalized.replace("BLE: ", "BLE ")
        elif lower.startswith("ble: scanning"):
            self.transport_desc = "BLE (scanning)"
        elif "ble" in lower and "not found" in lower:
            self.transport_desc = "BLE (reconnecting)"
        elif "falling back to serial" in lower:
            self.transport_desc = "Serial (connecting)"
        elif lower.startswith("ble unavailable"):
            self.transport_desc = "BLE (unavailable)"

    # ------------------------- Queue polling and plotting ---------------------

    def _drain_queue(self, source: "queue.Queue[str]") -> list[str]:
        items: list[str] = []
        while True:
            try:
                items.append(source.get_nowait())
            except queue.Empty:
                break
        return items

    def _poll_queues(self) -> None:
        processed = False
        cli_batch = self._drain_queue(self.cli_queue)
        if cli_batch:
            processed = True
            self._append_cli_output_batch(cli_batch)
            for entry in cli_batch:
                self._update_info_from_line(entry)

        monitor_batch = self._drain_queue(self.monitor_queue)
        if monitor_batch:
            processed = True
            self._append_monitor_batch(monitor_batch)
            for entry in monitor_batch:
                self._update_info_from_line(entry)

        status_batch = self._drain_queue(self.status_queue)
        for status in status_batch:
            processed = True
            self.status_label.setText(status)
            self._update_transport_from_status(status)
            self._refresh_info_bar()

        if processed:
            # throttle next spin if we were busy; timer interval is fixed
            pass

    def _update_plot(self) -> None:  # pragma: no cover
        (
            _fusion_quat,
            _sflp_quat,
            active,
            active_source,
            position,
            pos_ts,
            punch,
            punch_ts,
            magnetometer,
            mag_ts,
            flex_value,
            flex_raw,
            flex_midi,
            flex_ts,
        ) = self.telemetry.snapshot()
        now = time.time()

        pretty_source = getattr(self, "orientation_source", "Waiting")

        if active is not None:
            rot_active = quat_to_rotation_matrix(active)
            pointer = np.multiply(
                rot_active @ self.base_vec, self.orientation_radius
            )
            self.active_pointer_line.set_data([0.0, pointer[0]], [0.0, pointer[1]])
            cast(Any, self.active_pointer_line).set_3d_properties([0.0, pointer[2]])
            cast(Any, self.active_marker)._offsets3d = (
                [pointer[0]],
                [pointer[1]],
                [pointer[2]],
            )
            roll, pitch, yaw = self._quat_to_euler_deg(active)
            if active_source == "fusion":
                source_label = "Fusion"
            elif active_source == "sflp":
                source_label = "SFLP"
            else:
                source_label = "Unknown"
            self.active_angles_label.set_text(
                f"[{source_label}] Roll: {roll:+.1f} deg, Pitch: {pitch:+.1f} deg, Yaw: {yaw:+.1f} deg"
            )
            pretty_source = source_label
        else:
            self.active_angles_label.set_text("Active orientation unavailable")
            pretty_source = "Unavailable" if pretty_source != "Waiting" else "Waiting"

        self._update_punch_indicator(punch, punch_ts, now)
        self._update_compass(magnetometer, mag_ts, now)
        self._update_flex_meter(flex_value, flex_raw, flex_midi, flex_ts, now)

        if pretty_source != getattr(self, "orientation_source", ""):
            self.orientation_source = pretty_source
            self._refresh_info_bar()

        if position is not None and pos_ts > self.last_position_ts:
            self.last_position_ts = pos_ts
            self.position_trail.append(position)
            self.position_point.set_data([position[0]], [position[1]])
            cast(Any, self.position_point).set_3d_properties([position[2]])
            self.position_label.set_text(
                f"Pos: ({position[0]:+.2f}, {position[1]:+.2f}, {position[2]:+.2f})"
            )
            if self.position_trail:
                trail = np.vstack(self.position_trail)
                self.trail_line.set_data(trail[:, 0], trail[:, 1])
                cast(Any, self.trail_line).set_3d_properties(trail[:, 2])
                max_extent = float(np.max(np.abs(trail)))
                target = max(0.3, max_extent * 1.4)
                if target > 0 and abs(target - self._last_trail_radius) > 0.05:
                    self.ax_position.set_xlim([-target, target])
                    self.ax_position.set_ylim([-target, target])
                    self.ax_position.set_zlim([-target, target])
                    self._last_trail_radius = target

        self.canvas.draw_idle()

    @staticmethod
    def _quat_to_euler_deg(
        quat: Tuple[float, float, float, float],
    ) -> tuple[float, float, float]:
        w, x, y, z = quat
        t0 = 2.0 * (w * x + y * z)
        t1 = 1.0 - 2.0 * (x * x + y * y)
        roll = math.degrees(math.atan2(t0, t1))
        t2 = 2.0 * (w * y - z * x)
        t2 = max(-1.0, min(1.0, t2))
        pitch = math.degrees(math.asin(t2))
        t3 = 2.0 * (w * z + x * y)
        t4 = 1.0 - 2.0 * (y * y + z * z)
        yaw = math.degrees(math.atan2(t3, t4))
        return roll, pitch, yaw

    @staticmethod
    def _angles_to_direction(horizontal_deg: float, vertical_deg: float) -> np.ndarray:
        if not (math.isfinite(horizontal_deg) and math.isfinite(vertical_deg)):
            return np.zeros(3, dtype=float)
        horizontal_rad = math.radians(horizontal_deg)
        vertical_rad = math.radians(vertical_deg)
        cos_vertical = math.cos(vertical_rad)
        return np.array(
            [
                cos_vertical * math.cos(horizontal_rad),
                cos_vertical * math.sin(horizontal_rad),
                math.sin(vertical_rad),
            ],
            dtype=float,
        )

    def _update_punch_indicator(
        self,
        punch: Optional[Tuple[float, float, float]],
        punch_ts: float,
        now: float,
    ) -> None:
        if self.punch_line is None:
            return
        visible = False
        if punch is not None and self.punch_display_duration > 0.0:
            velocity, horizontal_deg, vertical_deg = punch
            if (
                velocity > 0.0
                and math.isfinite(velocity)
                and (now - punch_ts) <= self.punch_display_duration
            ):
                direction = self._angles_to_direction(horizontal_deg, vertical_deg)
                norm = float(np.linalg.norm(direction))
                if norm > 1e-6:
                    unit_dir = direction / norm
                    length_ratio = (
                        0.0
                        if self.punch_velocity_full_scale <= 0.0
                        else velocity / self.punch_velocity_full_scale
                    )
                    length_ratio = max(0.0, min(length_ratio, 1.5))
                    length = length_ratio * self.orientation_radius
                    endpoint = np.multiply(unit_dir, length)
                    self.punch_line.set_data(
                        [0.0, float(endpoint[0])], [0.0, float(endpoint[1])]
                    )
                    cast(Any, self.punch_line).set_3d_properties(
                        [0.0, float(endpoint[2])]
                    )
                    self.punch_line.set_visible(True)
                    self.punch_line.set_alpha(0.9)
                    visible = True
        if not visible:
            self.punch_line.set_visible(False)
            self.punch_line.set_alpha(0.0)
            self.punch_line.set_data([0.0, 0.0], [0.0, 0.0])
            cast(Any, self.punch_line).set_3d_properties([0.0, 0.0])

    def _update_compass(
        self, mag_vec: Optional[np.ndarray], mag_ts: float, now: float
    ) -> None:
        stale = mag_vec is None or mag_ts <= 0.0 or (now - mag_ts) > 3.0
        if stale:
            self.compass_line.set_visible(False)
            self.compass_marker.set_visible(False)
            self.compass_heading_label.set_text("Heading: --")
            self.compass_field_label.set_text("|B|: -- µT")
            return
        assert mag_vec is not None
        mag = np.asarray(mag_vec, dtype=float)
        mx, my, mz = (float(mag[0]), float(mag[1]), float(mag[2]))
        horizontal = np.array([mx, my], dtype=float)
        horizontal_norm = float(np.linalg.norm(horizontal))
        field_norm = float(np.linalg.norm(mag))
        if horizontal_norm < 1e-4:
            self.compass_line.set_visible(False)
            self.compass_marker.set_visible(False)
            self.compass_heading_label.set_text("Heading: --")
            self.compass_field_label.set_text(f"|B|: {field_norm:5.1f} µT")
            return
        unit = horizontal / horizontal_norm
        if self.compass_full_scale <= 0.0:
            length = self.compass_max_radius
        else:
            length = (
                min(horizontal_norm / self.compass_full_scale, 1.0)
                * self.compass_max_radius
            )
        endpoint = np.multiply(unit, length)
        self.compass_line.set_data([0.0, float(endpoint[0])], [0.0, float(endpoint[1])])
        self.compass_marker.set_data([float(endpoint[0])], [float(endpoint[1])])
        self.compass_line.set_visible(True)
        self.compass_marker.set_visible(True)
        heading_deg = math.degrees(math.atan2(unit[1], unit[0]))
        if heading_deg > 180.0:
            heading_deg -= 360.0
        elif heading_deg < -180.0:
            heading_deg += 360.0
        self.compass_heading_label.set_text(f"Heading: {heading_deg:+.1f}°")
        self.compass_field_label.set_text(f"|B|: {field_norm:5.1f} µT")

    def _update_flex_meter(
        self,
        flex_value: Optional[int],
        flex_raw: Optional[int],
        flex_midi: Optional[int],
        flex_ts: float,
        now: float,
    ) -> None:
        if self.flex_bar is None or self.flex_value_label is None:
            return
        stale = (
            flex_midi is None
            or flex_ts <= 0.0
            or (self.flex_meter_stale_timeout > 0.0 and (now - flex_ts) > self.flex_meter_stale_timeout)
        )
        if stale:
            self.flex_bar.set_width(0.0)
            self.flex_bar.set_alpha(0.2)
            self.flex_value_label.set_text("MIDI: --  Raw: --  Index: --")
            self.flex_value_label.set_color("#606060")
            return
        assert flex_midi is not None
        level = max(0, min(int(self.flex_meter_full_scale), int(flex_midi)))
        self.flex_bar.set_width(level)
        self.flex_bar.set_alpha(0.85)
        raw_display = "--" if flex_raw is None else f"{flex_raw}"
        index_display = "--" if flex_value is None else f"{flex_value}"
        self.flex_value_label.set_text(
            f"MIDI: {level:3d}  Raw: {raw_display}  Index: {index_display}"
        )
        self.flex_value_label.set_color("#1E90FF")

    # ------------------------- Close and save ---------------------------------

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._save_splitter_state()
        try:
            if isinstance(self.client, SerialTelemetryClient):
                self.client.stop()
            elif isinstance(self.client, BleTelemetryClient):
                self.client.stop()
        finally:
            super().closeEvent(event)


async def _resolve_ble_target_async(
    name_hint: Optional[str], address: Optional[str], scan_time: float
) -> tuple[Optional[str], list[str]]:
    # This helper mirrors the original behavior for BLE pre-resolution.
    try:
        from bleak import BleakScanner  # type: ignore[import]
    except Exception as exc:
        return None, [f"BLE unavailable: {exc}"]
    if address:
        return address, [f"BLE: connecting to {address} ..."]
    hint = (name_hint or BLE_DEFAULT_NAME_HINT).lower()
    logs = [f"BLE: scanning for devices matching '{hint}' ({scan_time:.1f}s timeout)"]

    def _matches(device, adv_data):
        name = (device.name or "").lower()
        adv_name = (adv_data.local_name or "").lower()
        return hint in name or hint in adv_name

    device = await BleakScanner.find_device_by_filter(_matches, timeout=scan_time)
    if not device:
        logs.append("BLE: device not found.")
        return None, logs
    logs.append(
        f"BLE: found {device.name or 'Unnamed'} ({device.address}). Connecting..."
    )
    return device.address, logs


def _resolve_ble_target_sync(
    name_hint: Optional[str], address: Optional[str], scan_time: float
) -> tuple[Optional[str], list[str]]:
    try:
        return asyncio.run(_resolve_ble_target_async(name_hint, address, scan_time))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(
                _resolve_ble_target_async(name_hint, address, scan_time)
            )
        finally:
            asyncio.set_event_loop(None)
            loop.close()


# ----------------------------- Args and main ----------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Qt dashboard for G-Love")
    parser.add_argument(
        "-p",
        "--port",
        type=str,
        default=None,
        help="Serial port (auto-detect if not set)",
    )
    parser.add_argument(
        "-b",
        "--baud",
        type=int,
        default=115200,
        help="Serial baud rate (default: 115200)",
    )
    parser.add_argument(
        "--vector",
        type=float,
        nargs=3,
        default=[0.0, 0.0, 1.0],
        help="Base pointer vector to rotate (default: +Z)",
    )
    transport_group = parser.add_mutually_exclusive_group()
    transport_group.add_argument(
        "--ble", "--ble-only", dest="ble_only", action="store_true", help="Use BLE only"
    )
    transport_group.add_argument(
        "--serial",
        "--serial-only",
        dest="serial_only",
        action="store_true",
        help="Serial only",
    )
    parser.add_argument(
        "--ble-name", type=str, default=None, help="Substring of BLE name"
    )
    parser.add_argument(
        "--ble-address", type=str, default=None, help="BLE address/UUID"
    )
    parser.add_argument(
        "--ble-scan-time", type=float, default=5.0, help="Seconds to scan for BLE"
    )
    parser.add_argument(
        "--ble-timeout",
        type=float,
        default=30.0,
        help="BLE connection timeout in seconds",
    )
    parser.add_argument(
        "--show-logs",
        action="store_true",
        help="Display all ESP_LOG output in CLI pane",
    )
    parser.add_argument(
        "--log-tags",
        type=str,
        default=None,
        help="Comma-separated ESP_LOG tags to surface",
    )
    args = parser.parse_args()
    if not hasattr(args, "ble_only"):
        args.ble_only = False
    if not hasattr(args, "serial_only"):
        args.serial_only = False
    return args


def main() -> None:
    args = _parse_args()
    version_str = QtCore.qVersion()
    try:
        version_tuple = tuple(int(part) for part in version_str.split(".")[:3])
    except ValueError:
        version_tuple = (0, 0, 0)
    if version_tuple < (6, 0, 0):
        raise RuntimeError(
            f"PySide6 / Qt 6.0 or newer is required (detected Qt {version_str!r})"
        )
    app = QtWidgets.QApplication(sys.argv)
    win = DashboardWindow(args)
    win.resize(1280, 820)
    win.show()
    # Let SIGINT close the app from terminal
    timer = QtCore.QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
