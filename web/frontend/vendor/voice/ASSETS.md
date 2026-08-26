# Voice runtime assets

These files are pinned local copies used by `call_silero_vad.js` so first use
does not depend on a public CDN.

- `onnxruntime-web` 1.19.2: `ort.min.js`, both SIMD-threaded WASM/MJS pairs.
- `@ricky0123/vad-web` 0.0.22: `bundle.min.js`, AudioWorklet, Silero VAD v5 ONNX.

SHA-256 values:

```text
bundle.min.js                       5CCC5D17EF04F3D7259E0D1B317B23A868FA366E568C11D32B956F7D7D36E9C7
ort-wasm-simd-threaded.jsep.mjs     77696CB006548C3C18EF4372A27A3624F8A63AA3C4EEE060F2700FF2A2687CC3
ort-wasm-simd-threaded.jsep.wasm    3864394A1135425A4C9CF7EE844300DE3C182A7A04BF64B7EA7691151FEA714C
ort-wasm-simd-threaded.mjs          D870A377322C3053FB97432D548423F165DD15E2AF232947592FC07B0D2F3639
ort-wasm-simd-threaded.wasm         1BF0B9ED7AD025CF9CA88CE6DA29E54DF3F128A169F8241D71823E81F078D578
ort.min.js                          6C5E8696A7993C8AF6BBF7666A8ACF7F3179165939D9DBA459506A59C178061A
silero_vad_v5.onnx                  2623A2953F6FF3D2C1E61740C6CDB7168133479B267DFEF114A4A3CC5BDD788F
vad.worklet.bundle.min.js           D520FD351C99BA1553FFBCFA19302F2674706689705D1948C3DCA07FB408E0B7
```
