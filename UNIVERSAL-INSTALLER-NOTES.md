# Universal installer design and validation checklist

This installer is a **fat package containing two architecture-specific app bundles**, not a single universal2 app. That avoids assuming that PySide6, PortAudio/sounddevice, CTranslate2, Vosk, and other native dependencies can all be combined into one universal binary.

## Before deploying

- [ ] Build Intel bundle on a real Intel Mac (`uname -m` = `x86_64`).
- [ ] Build Apple Silicon bundle on a real Apple Silicon Mac (`uname -m` = `arm64`).
- [ ] Confirm both `universal-build/architectures/*/WING Voice Assistant.app` bundles launch without a development Python installation.
- [ ] Confirm local Vosk and Whisper model paths are present and first transcription works offline after the build.
- [ ] Install the generated PKG on one Intel Mac and one Apple Silicon Mac; confirm the correct architecture is selected.
- [ ] Confirm macOS microphone permission, DVS device enumeration, chosen channel indices, and return-audio isolation.
- [ ] Keep `writesEnabled` false; verify exact MCP tools/schemas and all six IEM bus indices before any write testing.
- [ ] Test at low monitor levels with the physical WING and Dante routing; no hardware test is implied by this project.

## What this does not do

- Does not package the separately configured WING MCP gateway or Node runtime.
- Does not guess bus indices, MCP tool names, channel mappings, or local private configuration.
- Does not enable live writes automatically or validate the actual console.
- Does not sign or notarize the application. For distribution beyond a trusted test Mac, sign and notarize using an appropriate Apple Developer ID workflow.
