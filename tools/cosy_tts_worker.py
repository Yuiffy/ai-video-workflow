"""Natural CosyVoice 3 cloning in its isolated runtime, from the model repo cwd."""
import argparse
import json
import sys
import time
from functools import partial
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8-sig"))
    root = Path.cwd()
    sys.path.insert(0, str(root / "third_party/Matcha-TTS"))
    import torch
    import numpy as np
    import soundfile as sf
    import wetext.wetext as wetext_impl
    # Use the installed text resources without checking the remote model hub.
    wetext_impl.snapshot_download = partial(wetext_impl.snapshot_download, local_files_only=True)
    from cosyvoice.cli.cosyvoice import AutoModel
    from cosyvoice.utils.common import set_all_random_seed

    if not torch.cuda.is_available():
        raise RuntimeError("This installation requires its configured CUDA GPU")
    start = time.monotonic()
    model = AutoModel(model_dir=str(root / "pretrained_models/Fun-CosyVoice3-0.5B"),
                      fp16=True, load_trt=False, load_vllm=False)
    set_all_random_seed(20261007)
    chunks = list(model.inference_zero_shot(
        request["text"], "You are a helpful assistant.<|endofprompt|>" + request["reference_text"],
        request["reference"], stream=False, speed=request.get("speed", 1.0),
        text_frontend=request.get("text_frontend", True)))
    wave = torch.cat([chunk["tts_speech"].cpu() for chunk in chunks], dim=1).squeeze().numpy()
    if not np.isfinite(wave).all() or wave.size == 0:
        raise RuntimeError("CosyVoice returned invalid audio")
    sf.write(request["output"], wave, model.sample_rate)
    print(json.dumps({"seconds": round(time.monotonic() - start, 2),
                      "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 1024**3, 2)}))


if __name__ == "__main__":
    main()
