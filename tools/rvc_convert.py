"""Command-line bridge for the installed RVC WebUI runtime.

This deliberately imports the user's local RVC checkout at runtime. The checkout,
weights and index files stay outside this repository.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rvc-root", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--index", default="")
    parser.add_argument("--pitch", type=int, default=0)
    parser.add_argument("--f0-method", default="rmvpe")
    parser.add_argument("--index-rate", type=float, default=0.75)
    parser.add_argument("--protect", type=float, default=0.33)
    args = parser.parse_args()
    args.input = str(Path(args.input).resolve())
    args.output = str(Path(args.output).resolve())
    if args.index:
        args.index = str(Path(args.index).resolve())
        if not Path(args.index).is_file():
            raise FileNotFoundError(args.index)
    root = Path(args.rvc_root).resolve()
    os.chdir(root)
    sys.path.insert(0, str(root))
    os.environ.setdefault("weight_root", str(root / "assets" / "weights"))
    os.environ.setdefault("rmvpe_root", str(root / "assets" / "rmvpe"))

    import numpy as np
    import soundfile as sf
    import torch
    from infer.lib.audio import load_audio
    from infer.lib.infer_pack.models import SynthesizerTrnMs256NSFsid, SynthesizerTrnMs768NSFsid
    from infer.lib.infer_pack.models import SynthesizerTrnMs256NSFsid_nono, SynthesizerTrnMs768NSFsid_nono
    from infer.modules.vc.pipeline import Pipeline
    from infer.modules.vc.utils import load_hubert

    device = "cuda" if torch.cuda.is_available() else "cpu"
    is_half = device == "cuda"
    weight_root = root / "assets" / "weights"
    model_path = Path(args.model)
    if not model_path.is_absolute():
        model_path = weight_root / model_path
    cpt = torch.load(model_path, map_location="cpu")
    tgt_sr = cpt["config"][-1]
    cpt["config"][-3] = cpt["weight"]["emb_g.weight"].shape[0]
    if_f0 = cpt.get("f0", 1)
    version = cpt.get("version", "v1")
    cls = {("v1", 1): SynthesizerTrnMs256NSFsid, ("v2", 1): SynthesizerTrnMs768NSFsid,
           ("v1", 0): SynthesizerTrnMs256NSFsid_nono, ("v2", 0): SynthesizerTrnMs768NSFsid_nono}[(version, if_f0)]
    net_g = cls(*cpt["config"], is_half=is_half) if if_f0 else cls(*cpt["config"])
    del net_g.enc_q
    net_g.load_state_dict(cpt["weight"], strict=False)
    net_g.eval().to(device)
    if is_half:
        net_g = net_g.half()
    else:
        net_g = net_g.float()

    class Config:
        x_pad, x_query, x_center, x_max = 3, 10, 60, 180
    rvc_config = Config()
    rvc_config.is_half = is_half
    rvc_config.device = device

    audio = load_audio(str(Path(args.input)), 16000)
    peak = np.abs(audio).max() / 0.95
    if peak > 1:
        audio /= peak
    index = args.index if args.index and Path(args.index).exists() else ""
    times = [0, 0, 0]
    output = Pipeline(tgt_sr, rvc_config).pipeline(load_hubert(rvc_config), net_g, 0, audio, str(args.input), times, args.pitch, args.f0_method, index, args.index_rate, if_f0, 3, tgt_sr, 0, 1.0, version, args.protect, None)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    sf.write(target, output, tgt_sr)
    print(f"converted: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
