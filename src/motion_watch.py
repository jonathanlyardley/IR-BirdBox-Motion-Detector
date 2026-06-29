#!/usr/bin/env python3
"""IR BirdBox motion detection with optional local live view.

This public starter script is deliberately configurable. Put private paths,
hostnames, email details, and hardware choices in .env rather than in code.
"""

from __future__ import annotations

import glob
import os
import smtplib
import subprocess
import threading
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import simplejpeg


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def _read_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def _load_env_file() -> dict[str, str]:
    script_dir = Path(__file__).resolve().parent
    candidates = [
        Path(os.environ["BIRDBOX_ENV_FILE"]) if os.environ.get("BIRDBOX_ENV_FILE") else None,
        Path.cwd() / ".env",
        script_dir / ".env",
        script_dir.parent / ".env",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return _read_env_file(candidate)
    return {}


_ENV = _load_env_file()


def env_str(name: str, default: str) -> str:
    return os.environ.get(name, _ENV.get(name, default))


def env_int(name: str, default: int) -> int:
    return int(env_str(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(env_str(name, str(default)))


def env_bool(name: str, default: bool) -> bool:
    value = env_str(name, "1" if default else "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def env_path(name: str, default: Path) -> Path:
    return Path(env_str(name, str(default))).expanduser()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


ROOT = env_path("BIRDBOX_ROOT", Path.home() / "birdbox")
CLIPS_DIR = env_path("BIRDBOX_CLIPS_DIR", ROOT / "clips")
LOG_FILE = env_path("BIRDBOX_LOG_FILE", ROOT / "logs" / "events.log")
RECORD_SCRIPT = env_path("BIRDBOX_RECORD_SCRIPT", ROOT / "bin" / "record15.sh")

IR_GPIO_PIN = env_int("BIRDBOX_IR_GPIO_PIN", 18)
STREAM_HOST = env_str("BIRDBOX_STREAM_HOST", "birdbox.local")
STREAM_PORT = env_int("BIRDBOX_STREAM_PORT", 8080)
STREAM_TIMEOUT_SECS = env_int("BIRDBOX_STREAM_TIMEOUT_SECS", 90)

WATCH_W = env_int("BIRDBOX_WATCH_WIDTH", 480)
WATCH_H = env_int("BIRDBOX_WATCH_HEIGHT", 270)
WATCH_FPS = env_int("BIRDBOX_WATCH_FPS", 3)
STREAM_W = env_int("BIRDBOX_STREAM_WIDTH", 1280)
STREAM_H = env_int("BIRDBOX_STREAM_HEIGHT", 720)
STREAM_FPS = env_int("BIRDBOX_STREAM_FPS", 10)

# Tuned starter thresholds from a real small-box IR deployment.
BRIGHT_THRESH_SCORE = env_float("BIRDBOX_BRIGHT_THRESH_SCORE", 4.0)
BRIGHT_PIXEL_DIFF = env_int("BIRDBOX_BRIGHT_PIXEL_DIFF", 9)
BRIGHT_FRACTION_THRESH = env_float("BIRDBOX_BRIGHT_FRACTION_THRESH", 0.050)
BRIGHT_CONFIRM_FRAMES = env_int("BIRDBOX_BRIGHT_CONFIRM_FRAMES", 4)
BRIGHT_MIN_MEAN_JUMP = env_float("BIRDBOX_BRIGHT_MIN_MEAN_JUMP", 2.5)

DARK_THRESH_SCORE = env_float("BIRDBOX_DARK_THRESH_SCORE", 1.5)
DARK_PIXEL_DIFF = env_int("BIRDBOX_DARK_PIXEL_DIFF", 9)
DARK_FRACTION_THRESH = env_float("BIRDBOX_DARK_FRACTION_THRESH", 0.007)
DARK_CONFIRM_FRAMES = env_int("BIRDBOX_DARK_CONFIRM_FRAMES", 3)

DARK_ENTER_MEAN = env_float("BIRDBOX_DARK_ENTER_MEAN", 7.0)
DARK_EXIT_MEAN = env_float("BIRDBOX_DARK_EXIT_MEAN", 9.0)
BRIGHTNESS_EMA_ALPHA = env_float("BIRDBOX_BRIGHTNESS_EMA_ALPHA", 0.20)

IR_WARMUP_SECS = env_float("BIRDBOX_IR_WARMUP_SECS", 3.0)
IR_SETTLE_DROP_FRAMES = env_int("BIRDBOX_IR_SETTLE_DROP_FRAMES", 6)
START_DROP_FRAMES = env_int("BIRDBOX_START_DROP_FRAMES", 2)
MIN_SECONDS_BETWEEN_TRIGGERS = env_float("BIRDBOX_MIN_SECONDS_BETWEEN_TRIGGERS", 60.0)
COOLDOWN_SEC = env_float("BIRDBOX_COOLDOWN_SEC", 5.0)

IGNORE_GLOBAL_LIGHT = env_bool("BIRDBOX_IGNORE_GLOBAL_LIGHT", True)
GLOBAL_LIGHT_MEAN_JUMP = env_float("BIRDBOX_GLOBAL_LIGHT_MEAN_JUMP", 12.0)
GLOBAL_LIGHT_FRAC = env_float("BIRDBOX_GLOBAL_LIGHT_FRAC", 0.08)
BRIGHT_UNSTABLE_B_DIFF = env_float("BIRDBOX_BRIGHT_UNSTABLE_B_DIFF", 20.0)
BRIGHT_SHADOW_IGNORE_MEANJUMP = env_float("BIRDBOX_BRIGHT_SHADOW_IGNORE_MEANJUMP", 8.0)
BRIGHT_SHADOW_IGNORE_FRAC = env_float("BIRDBOX_BRIGHT_SHADOW_IGNORE_FRAC", 0.080)
BRIGHT_SHADOW_MAX_SCORE = env_float("BIRDBOX_BRIGHT_SHADOW_MAX_SCORE", 7.0)
BRIGHT_REFLECTION_B_DIFF = env_float("BIRDBOX_BRIGHT_REFLECTION_B_DIFF", 8.0)
BRIGHT_REFLECTION_MIN_FRAC = env_float("BIRDBOX_BRIGHT_REFLECTION_MIN_FRAC", 0.120)
BRIGHT_REFLECTION_MAX_SCORE = env_float("BIRDBOX_BRIGHT_REFLECTION_MAX_SCORE", 6.0)
BRIGHT_REFLECTION_MAX_MEANJUMP = env_float("BIRDBOX_BRIGHT_REFLECTION_MAX_MEANJUMP", 5.5)
SENSOR_NOISE_MAX_SCORE = env_float("BIRDBOX_SENSOR_NOISE_MAX_SCORE", 3.0)
SENSOR_NOISE_MIN_FRAC = env_float("BIRDBOX_SENSOR_NOISE_MIN_FRAC", 0.15)

EMAIL_ENABLED = env_bool("BIRDBOX_EMAIL_ENABLED", True)
EMAIL_COOLDOWN_SECS = env_float("BIRDBOX_EMAIL_COOLDOWN_SECS", 300.0)
SMTP_HOST = env_str("BIRDBOX_SMTP_HOST", "")
SMTP_PORT = env_int("BIRDBOX_SMTP_PORT", 465)
EMAIL_FROM = env_str("BIRDBOX_EMAIL_FROM", "")
EMAIL_PASSWORD = env_str("BIRDBOX_EMAIL_PASSWORD", "")
EMAIL_TO = [item.strip() for item in env_str("BIRDBOX_EMAIL_TO", "").split(",") if item.strip()]
MAX_EMAIL_CLIP_MB = env_float("BIRDBOX_MAX_EMAIL_CLIP_MB", 20.0)

STATUS_EVERY_SECS = env_float("BIRDBOX_STATUS_EVERY_SECS", 20.0)
RESTART_DELAY_SEC = env_float("BIRDBOX_RESTART_DELAY_SEC", 2.0)
PRINT_DEBUG = env_bool("BIRDBOX_PRINT_DEBUG", True)


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------


_brightness_ema: float | None = None
_is_dark = False
_ir_is_on = False
_last_status = 0.0
_last_email_time = 0.0
_last_ignore_log = 0.0

_stream_requested = threading.Event()
_stream_active = threading.Event()
_stream_frame_lock = threading.Condition()
_stream_latest_frame: bytes | None = None


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{timestamp} {message}\n")


def run_quiet(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def ir_on() -> None:
    global _ir_is_on
    run_quiet(["pinctrl", "set", str(IR_GPIO_PIN), "dh"])
    _ir_is_on = True


def ir_off() -> None:
    global _ir_is_on
    run_quiet(["pinctrl", "set", str(IR_GPIO_PIN), "dl"])
    _ir_is_on = False


def terminate_proc(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()


def start_camera(width: int, height: int, fps: int) -> subprocess.Popen:
    run_quiet(["pkill", "-f", "rpicam-vid"])
    time.sleep(0.5)
    cmd = [
        "rpicam-vid",
        "-t", "0",
        "--nopreview",
        "--autofocus-mode", "manual",
        "--lens-position", "7",
        "--codec", "mjpeg",
        "--width", str(width),
        "--height", str(height),
        "--framerate", str(fps),
        "-o", "-",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)


def next_jpeg(proc: subprocess.Popen) -> bytes | None:
    buf = b""
    while True:
        if proc.stdout is None:
            return None
        chunk = proc.stdout.read(4096)
        if not chunk:
            return None
        buf += chunk
        start = buf.find(b"\xff\xd8")
        if start == -1:
            buf = buf[-2048:]
            continue
        end = buf.find(b"\xff\xd9", start)
        if end == -1:
            continue
        return buf[start:end + 2]


def decode_gray(jpeg: bytes) -> np.ndarray:
    return simplejpeg.decode_jpeg(jpeg, colorspace="GRAY")


def motion_metrics(prev_gray: np.ndarray, gray: np.ndarray, pixel_diff: int) -> tuple[float, float, float]:
    a = prev_gray[::2, ::2].astype(np.int16)
    b = gray[::2, ::2].astype(np.int16)
    mean_a = float(a.mean())
    mean_b = float(b.mean())
    mean_jump = abs(mean_b - mean_a)
    diff = np.abs((a - int(mean_a)) - (b - int(mean_b)))
    score = float(diff.mean())
    frac = float(np.mean(diff > pixel_diff))
    return score, frac, mean_jump


def update_dark_mode(gray: np.ndarray) -> float:
    global _brightness_ema, _is_dark
    mean_now = float(gray[::8, ::8].mean())
    if _brightness_ema is None:
        _brightness_ema = mean_now
    else:
        _brightness_ema = (BRIGHTNESS_EMA_ALPHA * mean_now) + ((1 - BRIGHTNESS_EMA_ALPHA) * _brightness_ema)

    was_dark = _is_dark
    if not _is_dark and _brightness_ema <= DARK_ENTER_MEAN:
        _is_dark = True
    elif _is_dark and _brightness_ema >= DARK_EXIT_MEAN:
        _is_dark = False
    if _is_dark != was_dark:
        log(f"MODE {'DARK' if _is_dark else 'BRIGHT'} brightness_ema={_brightness_ema:.1f}")
    return mean_now


def current_profile() -> tuple[float, int, float, int]:
    if _is_dark:
        return DARK_THRESH_SCORE, DARK_PIXEL_DIFF, DARK_FRACTION_THRESH, DARK_CONFIRM_FRAMES
    return BRIGHT_THRESH_SCORE, BRIGHT_PIXEL_DIFF, BRIGHT_FRACTION_THRESH, BRIGHT_CONFIRM_FRAMES


def should_ignore(score: float, frac: float, mean_jump: float, brightness: float) -> str | None:
    global _last_ignore_log
    ema = _brightness_ema if _brightness_ema is not None else brightness

    if IGNORE_GLOBAL_LIGHT and mean_jump >= GLOBAL_LIGHT_MEAN_JUMP and frac >= GLOBAL_LIGHT_FRAC:
        return "global_light"
    if score <= SENSOR_NOISE_MAX_SCORE and frac >= SENSOR_NOISE_MIN_FRAC:
        return "sensor_noise"
    if not _is_dark and mean_jump >= BRIGHT_SHADOW_IGNORE_MEANJUMP and frac >= BRIGHT_SHADOW_IGNORE_FRAC and score < BRIGHT_SHADOW_MAX_SCORE:
        return "shadow"
    if not _is_dark and abs(brightness - ema) >= BRIGHT_UNSTABLE_B_DIFF and score < 5.0:
        return "unstable_brightness"
    if (
        not _is_dark
        and abs(brightness - ema) >= BRIGHT_REFLECTION_B_DIFF
        and frac >= BRIGHT_REFLECTION_MIN_FRAC
        and score < BRIGHT_REFLECTION_MAX_SCORE
        and mean_jump < BRIGHT_REFLECTION_MAX_MEANJUMP
    ):
        return "reflection"
    return None


def record_clip() -> None:
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["/usr/bin/bash", str(RECORD_SCRIPT)], check=False)
    log(f"RECORD exit_code={result.returncode}")


def latest_clip() -> Path | None:
    clips = sorted(glob.glob(str(CLIPS_DIR / "*.mp4")), key=os.path.getmtime)
    return Path(clips[-1]) if clips else None


# ---------------------------------------------------------------------------
# Optional email
# ---------------------------------------------------------------------------


def email_is_configured() -> bool:
    return bool(EMAIL_ENABLED and SMTP_HOST and EMAIL_FROM and EMAIL_PASSWORD and EMAIL_TO)


def extract_still(clip_path: Path) -> Path | None:
    still_path = clip_path.with_name(f"{clip_path.stem}_thumb.jpg")
    result = subprocess.run(
        ["/usr/bin/ffmpeg", "-nostdin", "-y", "-ss", "1", "-i", str(clip_path), "-vframes", "1", "-q:v", "3", str(still_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0 and still_path.exists() and still_path.stat().st_size > 1000:
        return still_path
    try:
        still_path.unlink(missing_ok=True)
    except Exception:
        pass
    return None


def send_motion_email(clip_path: Path, mode: str, score: float) -> None:
    global _last_email_time
    if not email_is_configured():
        return
    now = time.time()
    if now - _last_email_time < EMAIL_COOLDOWN_SECS:
        return
    _last_email_time = now

    def _send() -> None:
        try:
            clip_name = clip_path.name
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            msg = MIMEMultipart()
            msg["From"] = EMAIL_FROM
            msg["To"] = ", ".join(EMAIL_TO)
            msg["Subject"] = f"BirdBox motion detected - {timestamp}"

            attached_clip = False
            if clip_path.exists() and clip_path.stat().st_size <= MAX_EMAIL_CLIP_MB * 1024 * 1024:
                with clip_path.open("rb") as f:
                    part = MIMEBase("video", "mp4")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", "attachment", filename=clip_name)
                msg.attach(part)
                attached_clip = True

            still_path = None
            if not attached_clip:
                still_path = extract_still(clip_path)
                if still_path:
                    with still_path.open("rb") as f:
                        msg.attach(MIMEImage(f.read(), _subtype="jpeg", name=still_path.name))

            body = (
                "Motion detected in the birdbox.\n\n"
                f"Time: {timestamp}\n"
                f"Mode: {mode}\n"
                f"Score: {score:.2f}\n"
                f"Clip: {clip_name}\n\n"
                f"Local stream: http://{STREAM_HOST}:{STREAM_PORT}/\n"
            )
            msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
                server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
            if still_path:
                still_path.unlink(missing_ok=True)
            log("EMAIL sent")
        except Exception as exc:
            log(f"EMAIL failed: {exc}")

    threading.Thread(target=_send, daemon=True).start()


# ---------------------------------------------------------------------------
# Local MJPEG live view
# ---------------------------------------------------------------------------


_STREAM_PAGE = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BirdBox Live</title>
  <style>
    body {{ margin: 0; padding: 16px; background: #111; color: #eee; font-family: sans-serif; text-align: center; }}
    h1 {{ font-size: 1.4rem; margin: 0 0 12px; }}
    img {{ max-width: 100%; height: auto; border: 2px solid #333; }}
    p {{ opacity: 0.72; }}
  </style>
</head>
<body>
  <h1>BirdBox Live</h1>
  <img src="/stream.mjpg" alt="BirdBox live stream">
  <p>Motion detection pauses while live view is active. Stream stops after {STREAM_TIMEOUT_SECS} seconds.</p>
</body>
</html>
"""


def _stream_frame_grabber(proc: subprocess.Popen, stop_event: threading.Event) -> None:
    global _stream_latest_frame
    while not stop_event.is_set():
        frame = next_jpeg(proc)
        if frame is None:
            break
        with _stream_frame_lock:
            _stream_latest_frame = frame
            _stream_frame_lock.notify_all()
    with _stream_frame_lock:
        _stream_latest_frame = None
        _stream_frame_lock.notify_all()


class StreamHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            content = _STREAM_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if self.path.startswith("/stream.mjpg"):
            _stream_requested.set()
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            deadline = time.time() + 15
            while not _stream_active.is_set() and time.time() < deadline:
                time.sleep(0.2)
            try:
                while _stream_active.is_set():
                    with _stream_frame_lock:
                        _stream_frame_lock.wait(timeout=5)
                        frame = _stream_latest_frame
                    if frame is None:
                        break
                    self.wfile.write(b"--FRAME\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        return


def start_http_server() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", STREAM_PORT), StreamHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log(f"STREAM server ready on port {STREAM_PORT}")


def run_stream_mode() -> None:
    global _stream_latest_frame
    log(f"STREAM start for {STREAM_TIMEOUT_SECS}s")
    run_quiet(["pkill", "-f", "rpicam-vid"])
    ir_on()
    proc = start_camera(STREAM_W, STREAM_H, STREAM_FPS)
    stop_event = threading.Event()
    threading.Thread(target=_stream_frame_grabber, args=(proc, stop_event), daemon=True).start()
    _stream_active.set()
    try:
        deadline = time.time() + STREAM_TIMEOUT_SECS
        while time.time() < deadline:
            time.sleep(1)
    finally:
        stop_event.set()
        _stream_active.clear()
        _stream_requested.clear()
        with _stream_frame_lock:
            _stream_latest_frame = None
            _stream_frame_lock.notify_all()
        terminate_proc(proc)
        ir_off()
        log("STREAM ended")


# ---------------------------------------------------------------------------
# Main detector loop
# ---------------------------------------------------------------------------


def detection_cycle() -> None:
    global _last_status, _last_ignore_log
    proc = start_camera(WATCH_W, WATCH_H, WATCH_FPS)
    try:
        for _ in range(START_DROP_FRAMES):
            frame = next_jpeg(proc)
            if frame is None:
                return
            decode_gray(frame)

        prev: np.ndarray | None = None
        confirm_hits = 0
        last_trigger = 0.0

        while True:
            if _stream_requested.is_set():
                return

            frame = next_jpeg(proc)
            if frame is None:
                log("WATCH stream ended unexpectedly")
                return
            gray = decode_gray(frame)
            brightness = update_dark_mode(gray)

            if _is_dark and not _ir_is_on:
                terminate_proc(proc)
                ir_on()
                time.sleep(IR_WARMUP_SECS)
                proc = start_camera(WATCH_W, WATCH_H, WATCH_FPS)
                for _ in range(IR_SETTLE_DROP_FRAMES):
                    warm_frame = next_jpeg(proc)
                    if warm_frame:
                        prev = decode_gray(warm_frame)
                continue
            if not _is_dark and _ir_is_on:
                ir_off()

            now = time.time()
            if now - _last_status >= STATUS_EVERY_SECS:
                log(f"STATUS mode={'DARK' if _is_dark else 'BRIGHT'} brightness={brightness:.1f} ir={'ON' if _ir_is_on else 'OFF'}")
                _last_status = now

            if prev is None:
                prev = gray
                continue

            thresh_score, pixel_diff, frac_thresh, confirm_frames = current_profile()
            score, frac, mean_jump = motion_metrics(prev, gray, pixel_diff)
            ignore_reason = should_ignore(score, frac, mean_jump, brightness)
            if ignore_reason:
                confirm_hits = 0
                if now - _last_ignore_log >= 5:
                    log(f"IGNORE {ignore_reason} score={score:.1f} frac={frac:.3f} mean_jump={mean_jump:.1f}")
                    _last_ignore_log = now
                prev = gray
                continue

            if _is_dark:
                triggered = score >= thresh_score and frac >= frac_thresh
            else:
                triggered = score >= thresh_score and frac >= frac_thresh and mean_jump >= BRIGHT_MIN_MEAN_JUMP
            confirm_hits = confirm_hits + 1 if triggered else 0

            if PRINT_DEBUG:
                print(
                    f"{'DARK' if _is_dark else 'BRI '} b={brightness:5.1f} "
                    f"score={score:5.1f} frac={frac * 100:5.2f}% hits={confirm_hits}/{confirm_frames}",
                    end="\r",
                )

            if confirm_hits >= confirm_frames and now - last_trigger >= MIN_SECONDS_BETWEEN_TRIGGERS:
                last_trigger = now
                confirm_hits = 0
                mode = "DARK" if _is_dark else "BRIGHT"
                log(f"MOTION detected mode={mode} score={score:.1f} frac={frac:.3f} mean_jump={mean_jump:.1f}")
                terminate_proc(proc)
                ir_off()
                record_clip()
                clip = latest_clip()
                if clip:
                    send_motion_email(clip, mode, score)
                time.sleep(COOLDOWN_SEC)
                return

            prev = gray
    finally:
        terminate_proc(proc)


def main() -> None:
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ir_off()
    if email_is_configured():
        log(f"EMAIL configured: {len(EMAIL_TO)} recipient(s)")
    else:
        log("EMAIL not configured - notifications disabled")
    start_http_server()
    log("MOTION start")

    while True:
        try:
            if _stream_requested.is_set():
                run_stream_mode()
            else:
                detection_cycle()
        except KeyboardInterrupt:
            log("MOTION stop requested")
            ir_off()
            return
        except Exception as exc:
            log(f"ERROR {exc}")
            ir_off()
            time.sleep(10)
        time.sleep(RESTART_DELAY_SEC)


if __name__ == "__main__":
    main()
