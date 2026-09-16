---
name: ai-video-workflow
description: Create narrated explainer videos with the AI Video Workflow repository, mixing authored HTML diagrams, Dreamina shots and local TTS/RVC. Use for project histories, science explainers and generated-video assembly.
---

# AI Video Workflow

Work from the repository root. Read README.md for commands and the selected
project.json for scene order, narration and local inputs. For history videos,
ground milestones in commits and the user's reference material; retain a source
map with the example rather than inventing dates from filenames.

Codex authors the script, prompts and HTML. Project JSON is the narration source
of truth; keep the readable script synchronized. Let each HTML scene explain one
idea with a diagram or concrete example. Generated footage can illustrate that
idea while the webpage owns precise text and relationships.

## Produce and review

- Run `python -m src.cli doctor`, then `plan <project.json> --dry-run`.
- Within the user's existing generation authorization, use `jimeng` to submit
  new scenes. It resumes saved IDs. `poll` refreshes and downloads those IDs.
  Timeout or stale list_task state is not grounds for a paid resubmission.
  Recover uncertain submissions with `adopt --scene ID --submit-id ID`.
- Use `voice` for TTS → RVC. RVC is voice conversion, so do not describe it as
  an independent TTS model. A voice reference alone is not proof of output voice;
  use `already_target_voice` only for a confirmed input or chosen TTS voice.
- HTML decks expose `window.renderAt({slide,time,duration})` and `[data-slide]`.
  The renderer records explicit frames, preserving narration length.
- Use `render` for mixed footage/HTML or `record` for an HTML-only video.
  The final MP4, SRT and timeline are under the project's ignored outputs.
- Inspect representative frames from every chapter, first/last frames, subtitle
  boundaries and audio duration. ASR can catch missing words but cannot prove
  natural voice quality. Do not claim to have listened if only ASR was checked.

Source code is public; local models, credentials, character references and
generated media stay ignored. A video-generation request does not itself authorize
posting the result to an external video platform.
