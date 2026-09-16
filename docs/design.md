# Why a small independent workflow

We reviewed [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo),
[ShortGPT](https://github.com/RayVentura/ShortGPT), and
[toki-plus/ai-video-workflow](https://github.com/toki-plus/ai-video-workflow).
MoneyPrinterTurbo combines scripts, footage, subtitles and music. ShortGPT has
editing, voice and persistent state abstractions. toki-plus connects several
generators through a PyQt interface and FFmpeg.

This project keeps a narrower implementation boundary: Codex authors a versioned
project and HTML explainer, the official Dreamina CLI owns authentication and
remote generation, a local TTS → RVC service owns narration, and FFmpeg owns the
edit. These projects provide useful design references, but their documented
workflows do not provide this exact combination. Maintaining an independent
small orchestration layer avoids bringing in their UI, stock sourcing, and
provider credentials. No source code or assets have been copied from them.

## Stage contracts

- Project JSON is the source of truth for narration and scene order.
- TTS produces speech; RVC changes an existing voice. RVC alone is not TTS.
- References condition Dreamina generation; a reference file alone does not prove
  that an audio output uses the desired voice. Explicitly mark the audio input
  as already using the target voice to bypass conversion.
- Every paid scene has a durable job record before submission. A recovered ID is
  polled; a timeout never causes automatic resubmission.
- Narration duration drives the edit. Generated clips are short inserts, while
  programmable HTML diagrams occupy the rest of a scene.
- The renderer never truncates a narration to fit a generated clip.
- Generated media, local configs, model weights and API responses stay ignored.
