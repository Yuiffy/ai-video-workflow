"""Run with IndexTTS's Python, from its repository root."""
import argparse
import json
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8-sig"))
    import torch
    from indextts.infer_v2_5 import IndexTTS2

    if not torch.cuda.is_available():
        raise RuntimeError("This local installation requires its configured CUDA GPU")
    started = time.monotonic()
    model = IndexTTS2(cfg_path="checkpoints/config.yaml", model_dir="checkpoints",
                      use_bf16=True, use_cuda_kernel=False, use_deepspeed=False,
                      use_accel=False, use_torch_compile=False, use_qwen_emo=False)
    model.infer(spk_audio_prompt=request["reference"], text=request["text"], lang="ZH",
                output_path=request["output"], duration_factor=1 / request.get("speed", 1),
                use_random=False, verbose=False)
    print(json.dumps({"seconds": round(time.monotonic() - started, 2),
                      "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 1024**3, 2)}))


if __name__ == "__main__":
    main()
