# IR BirdBox Motion Detector

A low-cost Raspberry Pi motion detector for an infrared nestbox or birdbox camera.

It watches a low-resolution camera stream, filters out common false triggers such as shadows, sensor noise, and IR warm-up artefacts, records short MP4 clips when motion is confirmed, and offers a temporary local MJPEG live view.

This is a practical starter project for hobbyists, ecologists, conservation groups, and citizen-science tinkerers who want a small offline-first wildlife camera rather than a cloud camera subscription.

## What It Does

- Runs on a Raspberry Pi with a camera module.
- Uses frame-difference motion detection tuned for a small birdbox scene.
- Switches between bright and dark sensitivity profiles.
- Turns an IR LED ring on for dark monitoring and local live view.
- Records short clips with `rpicam-vid`.
- Can send optional email notifications if you configure SMTP credentials.
- Serves a local browser stream at `http://<your-pi-hostname>:8080/`.

## Hardware

Typical setup:

- Raspberry Pi Zero 2 W or similar.
- Raspberry Pi camera module, ideally NoIR for IR illumination.
- IR LED ring connected to a controllable GPIO pin.
- Weatherproof enclosure and safe outdoor power supply.
- microSD card with Raspberry Pi OS.

This repository does not cover enclosure construction, mains wiring, or solar power design in detail. For outdoor deployments, use suitable waterproofing, strain relief, fusing, and local electrical safety guidance.

## Install On A Raspberry Pi

These commands assume the project lives at `/home/pi/birdbox`.

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip ffmpeg git

git clone https://github.com/jonathanlyardley/IR-BirdBox-Motion-Detector.git /home/pi/birdbox
cd /home/pi/birdbox

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

mkdir -p clips logs bin
cp examples/.env.example .env
cp examples/record15.sh bin/record15.sh
chmod +x bin/record15.sh
```

Edit `.env` before running:

```bash
nano .env
```

Important values:

- `BIRDBOX_ROOT`: project folder, usually `/home/pi/birdbox`.
- `BIRDBOX_STREAM_HOST`: hostname or local IP you will type in your browser.
- `BIRDBOX_IR_GPIO_PIN`: GPIO pin controlling the IR light.
- `BIRDBOX_WIFI_IDLE_AUTO_OFF`: keep `false` until you have working Wi-Fi services.
- `BIRDBOX_SMTP_HOST`: leave blank to disable email safely.

## Run Manually

Use this first, before installing the service:

```bash
cd /home/pi/birdbox
. .venv/bin/activate
python src/motion_watch.py
```

In another terminal:

```bash
tail -f logs/events.log
```

Open the local stream in a browser:

```text
http://birdbox.local:8080/
```

If your Pi does not resolve as `birdbox.local`, use the local hostname or IP you put in `.env`.

## Install As A Service

Only do this after manual running works.

```bash
sudo cp examples/birdbox.service /etc/systemd/system/birdbox.service
sudo systemctl daemon-reload
sudo systemctl enable --now birdbox.service
sudo systemctl status birdbox.service
```

Logs:

```bash
journalctl -u birdbox.service -n 100 --no-pager
tail -f /home/pi/birdbox/logs/events.log
```

## Extract Example Frames

The helper script extracts three JPEGs per MP4 clip, useful for manual review or later AI verification.

```bash
pip install -r requirements-tools.txt
python tools/extract_frames.py --clips-dir clips --frames-dir frames
```

The `clips/` and `frames/` folders are ignored by Git so private footage is not committed by accident.

## Common Faults

| Symptom | Check |
| --- | --- |
| No camera frames | Run a simple `rpicam-still` test first. Reseat the camera ribbon if needed. |
| IR does not appear to work | Check wiring, power, and `BIRDBOX_IR_GPIO_PIN`; GPIO state alone does not prove the LEDs are lit. |
| Too many false triggers | Review clips and logs before changing thresholds. Shadows and reflections can look like motion. |
| Live stream opens but detection pauses | This is expected. The single camera pipeline is borrowed for live view. |
| No emails | Confirm `BIRDBOX_SMTP_HOST`, sender, password/app password, and recipient are set in private `.env`. |

## Privacy, Wildlife, And Safety

- Do not publish raw nestbox footage unless you have deliberately reviewed it.
- Keep streams local unless you have thought through privacy, security, and bandwidth.
- Avoid disturbing active nests. Check local wildlife guidance before installing, inspecting, or modifying a box.
- Do not expose `.env`, passwords, email credentials, local network details, or SSH keys.
- This project is provided as a hobbyist/educational starter kit. You are responsible for safe installation and lawful use.

See [docs/security.md](docs/security.md) before publishing forks or sharing deployments.

## Licence

MIT. See [LICENSE](LICENSE).
