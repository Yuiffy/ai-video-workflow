---
name: ai-video-workflow
description: Operate the local AI video workflow to turn a structured project into script, RVC narration, web PPT recording, optional Jimeng/Seedance shots, and an FFmpeg render.
---

# AI video workflow skill

Use this skill for projects under `ai-video-workflow/projects/`.

## Workflow

1. Read `project.json`, `script.md`, and `storyboard.json` before changing prompts or timing.
2. Run `python -m src.cli plan <project.json> --dry-run` and inspect `outputs/plan.json`.
3. Generate narration through the local RVC service. If a scene declares `already_target_voice` or has a trusted voice reference, preserve it and skip conversion.
4. Open the scene's `ppt/index.html` in a browser for visual review. Use Playwright recording only after the slide timing and text are readable at 1920×1080.
5. Submit Jimeng tasks using the generated plan. Default to `seedance2.0fast_vip`; use `seedance2.0mini` when the user requests lower cost. Do not invent credentials or upload actions.
6. Render with FFmpeg, then inspect the final duration, audio presence, and first/last frames.

## Safety and review

- Keep provider calls opt-in; dry-run is the default for new projects.
- Preserve prompt, provider response, and local path in the manifest.
- Do not publish to Bilibili or any external platform without a separate explicit instruction.
- Treat voice references as rights-sensitive local assets and avoid copying them into Git.
