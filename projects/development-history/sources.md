# Content sources

This episode follows the developer's narrative in the supplied
[earlier conversation](https://chatgpt.com/share/6aaa1edf-7720-83e8-a0f2-1e63e539a607):
manual GPT web chat → danmaku preparation → ASR → highlights → Webhook automation
→ goodnight text and comics → clips. The later visual preference in that
conversation was cinematic anime Sui interacting with data; the technical diagrams
are authored as HTML so the text and relationships remain controllable.

Repository evidence: [Yuiffy/danmaku-to-summary-ts](https://github.com/Yuiffy/danmaku-to-summary-ts).
These are implementation milestones, not necessarily the first day an idea was tried.

| Stage | Evidence | What it establishes |
| --- | --- | --- |
| Manual GPT web chat | Developer's current request and earlier conversation | Personal origin story; no exact start date claimed |
| Initial code | [07e70a4](https://github.com/Yuiffy/danmaku-to-summary-ts/commit/07e70a4), 2024-10-15 | Minute grouping, duplicate counts, unique users and random dropping in do_danmaku_to_simple.js |
| Content selection refinements | [538864e](https://github.com/Yuiffy/danmaku-to-summary-ts/commit/538864e), 2025-09-04; [6ab11c3](https://github.com/Yuiffy/danmaku-to-summary-ts/commit/6ab11c3) | Target output rows and low-information filtering evolved after the initial version |
| ASR input | [2f34562](https://github.com/Yuiffy/danmaku-to-summary-ts/commit/2f34562), 2025-11-23 | ASR subtitle processing was added |
| Webhook | [28ba8e0](https://github.com/Yuiffy/danmaku-to-summary-ts/commit/28ba8e0), 2026-01-10 | HTTP receiver; subsequent commits adapt real DDTV events and file stability |
| Goodnight and comics | [e093982](https://github.com/Yuiffy/danmaku-to-summary-ts/commit/e093982), 2026-01-14 | AI goodnight and comic generation introduced incrementally |
| Multiple ASR backends | [ASR guide](https://github.com/Yuiffy/danmaku-to-summary-ts/blob/master/docs/asr-backends.md) | Whisper, Paraformer, SenseVoice and Fun-ASR-Nano are supported; no universal quality ranking claimed |
| Clips and review | [Editorial guide](https://github.com/Yuiffy/danmaku-to-summary-ts/blob/master/docs/topic-event-editorial.md) | Candidate workflow, corrections, subtitles and review |
| Later full-text experiments | [ab0bbb3](https://github.com/Yuiffy/danmaku-to-summary-ts/commit/ab0bbb3) | Some experimental flows retain complete subtitles/danmaku rather than filtering by heat |

Chat bubbles, heat curves and displayed example subtitles are illustrative, not
quotes or measured activity from a particular stream. Sui scenes are generated
concept illustrations. The narration is synthetic TTS followed by local RVC.
Local character references, voice weights and generated media are not distributed
under the source-code license.
