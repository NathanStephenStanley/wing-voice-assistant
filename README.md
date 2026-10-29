# WING Voice Assistant for macOS — Universal Installer Builder

A local voice-assistant app for a Behringer WING Rack, designed to use Dante Virtual Soundcard (DVS) and the existing `wing-rack-assistant` MCP gateway. This project can assemble **one installer for Intel and Apple Silicon Macs**. It is not a single universal2 executable: it includes two separately built `.app` bundles and the installer selects the matching native build on the target Mac.

## Build one installer for both Mac architectures (from your Intel Mac)

Use GitHub Actions to build both native variants in the cloud; you do **not** need an Apple Silicon Mac to build the installer.

1. Follow [`GITHUB-ACTIONS-BUILD.md`](GITHUB-ACTIONS-BUILD.md) to create a private GitHub repository and push this project from your Intel Mac.
2. In GitHub, open **Actions** → **Build WING Voice Assistant Universal Installer** → **Run workflow**.
3. Wait for the Intel build, Apple Silicon build, and packaging job to complete.
4. Download the `WING-Voice-Assistant-Universal-Installer` artifact from the completed run. It contains `WING-Voice-Assistant-Universal.pkg`.
5. Copy that installer to the church Mac and install it there.

The workflow uses separate hosted macOS runners for Intel (`macos-15-intel`) and Apple Silicon (`macos-15`), then packages both native `.app` bundles into one `.pkg`. The resulting package is not code-signed or notarized by default. It has not been tested against physical WING/Dante hardware. See `GITHUB-ACTIONS-BUILD.md` for details, billing notes, and safety checks.

**This is a setup-ready starter, not a verified live-console integration.** You must select the correct DVS CoreAudio devices, bundle the open-source Vosk English model for constrained `Wing` wake detection, configure the MCP gateway path and exact tool schemas, verify the six IEM bus mappings, and test at low levels before enabling writes. It has not been tested against your physical mixer.

## Safety model

- Wake word is **Wing**. Uses the open-source Vosk small English model with a constrained wake-word grammar; this is not a neural custom keyword detector and may need tuning in noisy rooms.
- After wake, it records one utterance, transcribes locally with faster-whisper, then stops listening while processing, speaking, or waiting for confirmation. No command queue is maintained.
- All live writes require an explicit spoken `confirm`; `cancel` rejects the pending change.
- `undo` is offered only when the app has recorded a verified before/after value and has a configured, tested reverse action. Unknown prior values are never guessed.
- Meter monitoring is read-only and disabled until the exact meter tool and schema are configured. It never auto-corrects mixer levels.
- Existing WING routing is not changed by the app. Keep assistant return audio out of the wake-listening bus.
- Writes are disabled by default. The existing MCP gateway's own `enableWrites` must also be explicitly enabled after testing.

## Architecture

Dante DVS CoreAudio input -> Vosk constrained wake detector -> single-utterance recording -> local faster-whisper transcription -> allowlisted intent parser -> confirmation gate -> existing WING MCP gateway -> verified WING tool. macOS `say` generates speech to a temporary AIFF file, which the app plays through the configured DVS output device.

## Requirements

- Intel or Apple Silicon Mac running a current macOS version (build a native bundle on each architecture for the combined installer).
- Dante Virtual Soundcard installed and configured for the required sample rate / channel count.
- The existing WING MCP gateway package must be present and configured. The installer builder does not package your separately configured WING MCP gateway or its console-specific tool mappings.
- A No wake-word service account is required; the Vosk English model is downloaded during the installer build.
- Internet access on first launch to download the selected faster-whisper model; subsequent transcription runs locally from the cached model.
- Python 3.11 recommended (3.10+ may work; faster-whisper dependencies can vary by Python version).

## Install

1. Unzip this folder somewhere stable, e.g. `~/Applications/wing-voice-assistant`.
2. Open Terminal and run:

   ```bash
   cd ~/Applications/wing-voice-assistant
   chmod +x install.command run.command
   ./install.command
   ```

3. The architecture build downloads the Vosk wake model and Whisper `base.en` model at build time.
4. Copy the examples and edit them:

   ```bash
   cp config/app.example.json config/app.json
   cp config/iem-profiles.example.json config/iem-profiles.json
   cp config/tool-map.example.json config/tool-map.json
   ```

5. Set the DVS input/output device names in the GUI. The all-in-one PKG bundles Python and the Python/native speech dependencies.
6. Set `mcpGatewayPath` in `config/app.json` to the absolute path of the existing `wing-rack-assistant` folder. Do not copy private `config/local.json` files into this archive.
7. Inspect actual MCP tools/schemas with `python -m wing_voice.cli inspect-tools`. Use that report to configure `config/tool-map.json`. The starter does not guess tool names or argument keys.
8. Fill in all six IEM labels and verified bus indices in `config/iem-profiles.json`. Never guess bus indices.
9. Start with `writesEnabled: false`. Test device selection and wake/recognition first. Then test read-only MCP calls. Only enable writes after verifying tool mappings, read-before-write and confirmation behavior with a non-critical target at low monitor levels.

## Commands supported by the intent parser

Examples (the exact target must exist in the profile config):

- “Wing, status”
- “Wing, turn up Keys 1 by 1 dB”
- “Wing, turn down Drums by 2 dB”
- “Wing, set Acoustic to minus 12 dB”
- “Wing, mute Keys 1” / “unmute Keys 1”
- “confirm” / “cancel”
- “undo”

The parser creates a proposed action only. A write is not sent until the user says `confirm`. For safe implementation, the tool map must provide a read action and a write action with explicit JSON argument templates and a target-index argument. If your upstream server has different semantics, adapt the mapping and test it before enabling writes.

## Audio setup and routing

- In DVS, configure a combined wake-listening bus that contains only the six talkback mics. The assistant return must **not** be routed into that bus.
- Set the app's `inputDeviceContains` to the DVS input device name. `inputChannels` selects zero-based CoreAudio channel indices; use only the channels that actually carry the six-mic combined bus, or list the six discrete mic channels if the WING/DVS routing presents them separately.
- Set `outputDeviceContains` to the DVS output device name and `outputChannels` to the dedicated WING input's Dante transmit channels. Verify this channel mapping with the mixer muted/at low level first.
- Keep DVS and the WING clock/sample rate consistent. The app resamples wake audio to Vosk's required rate. Local speech recognition uses a temporary recording and does not transmit audio to a cloud service.
- Keep the Mac's physical speakers muted/low during initial output tests to avoid feedback.

## Meter monitoring

Meter monitoring is a read-only framework, not enabled by default. Configure `meterRead` in `tool-map.json` only after inspecting the actual tool schema and calibrating the returned units. The default policy thresholds in `app.example.json` are examples, not universal thresholds. No automatic level or mute changes are made.

## Run / diagnostics

```bash
./run.command --help
# Within the venv, list devices:
.venv/bin/python -m wing_voice.cli devices
# Inspect MCP tool names and input schemas:
.venv/bin/python -m wing_voice.cli inspect-tools
# Validate configs without opening audio:
.venv/bin/python -m wing_voice.cli validate
# Start assistant (after all prerequisites/configs are set):
./run.command
```

## Known limitations

- The architecture build script downloads open-source Vosk and Whisper models during the build. The build host needs internet access; the installed app is intended to run those models locally.
- The MCP gateway must already be configured and able to launch the upstream WING MCP server.
- The exact WING tool names and JSON schemas depend on the upstream version. `tool-map.json` is deliberately explicit and starts unconfigured.
- Meter payload parsing is schema-dependent; no alert is enabled until configured and tested.
- The undo journal is in memory for the current app session only; restarting the app clears undo history.
- No hardware routing changes, live mixer writes, or physical WING tests were performed while building this package.

## GUI on macOS

This project includes a refreshed macOS-style GUI with a dark graphite palette, teal accents, a left navigation rail, compact status header, and a custom vector app icon. It can configure the assistant's Dante/CoreAudio input and output device names and channel numbers, WING IP and ports, the upstream WING MCP server and config paths, six named IEM profiles, voice settings, confirmation/undo policies, read-only meter thresholds, and the exact MCP tool map. It can start/stop the voice assistant, detect audio devices, inspect MCP tools, validate configuration, and display/export logs.

### Run the GUI from this source folder

```bash
./install.command
./gui.command
```

### Build a native macOS `.app`

On the Mac, run the build script from the project folder. If needed, make the scripts executable first:

```bash
chmod +x install.command gui.command build-macos-app.command
./build-macos-app.command
```

The build script prefers Python 3.12 (and avoids Python 3.14 for the audio/ONNX dependency install), generates `assets/AppIcon.icns` from the bundled SVG, then packages the GUI with PyInstaller.

The build produces `dist/WING Voice Assistant.app`. It is a local GUI shell that copies editable project files to `~/Library/Application Support/WING Voice Assistant/project` on first launch. Use **Install / repair runtime** in the Overview tab (or run that folder's `install.command`) to install the separate audio/speech dependencies. The packaged GUI is not code-signed or notarized; macOS may ask you to approve it when first opened.

### WING IP and Dante mapping

The GUI writes the WING address to `plugins.wing.host` in the selected upstream server `data/config.json`, along with the OSC and meter ports. It also writes the selected upstream paths and the independent gateway write gate to the existing `wing-rack-assistant/config/local.json`. Before changing these settings, stop the assistant and any separately running upstream server. The GUI makes a `.wing-assistant.bak` backup of the upstream config before it edits that file.

Dante channels in the GUI are 1-based; the existing voice backend stores them 0-based. Select only the combined six-mic talkback bus for input and a dedicated assistant-return channel for output. Do not route the return channel into the listening bus. All six IEM bus indices start blank and must be verified against the actual console before use.

**Safety status:** live writes are disabled by default in the voice app and in the gateway. The GUI enforces confirmation-required, no-queue, and undo-only-last-verified policies. Meter alerts are read-only. No hardware test is claimed; confirm routing and the exact MCP tool schemas at low levels before enabling either write gate.

### PKG installer

Run `./build-pkg-installer.command` on macOS after building the app. It uses Apple's `pkgbuild` to create `dist/WING-Voice-Assistant-Installer.pkg`, which installs the `.app` into `/Applications`. Use `./build-all-in-one-pkg.command` on an Apple Silicon Mac to build `dist/WING-Voice-Assistant-All-in-One.pkg`. It bundles a frozen Python runtime, audio/speech dependencies, Vosk wake model, and Whisper `base.en` model. The WING MCP gateway is still installation-specific and must be selected/configured in the GUI. Build and smoke-test on the target Mac before use; the package has not been validated against physical WING/Dante hardware.
