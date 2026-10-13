"""S2 Pro BF16 evaluation in Fish Speech's isolated Python, with its repo as cwd.

Keep the original weights, limit the context for short clips, and run codec and
transformer in separate GPU stages to fit a 16 GB card. No torch.compile.
"""
import argparse
import gc
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8-sig"))
    sys.path.insert(0, str(Path.cwd()))
    import numpy as np
    import soundfile as sf
    import torch
    from fish_speech.models.text2semantic.inference import (
        decode_one_token_ar, decode_to_audio, encode_audio, generate_long,
        load_codec_model,
    )
    from fish_speech.models.text2semantic.llama import DualARTransformer

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required by this evaluation worker")
    torch.set_num_threads(8)
    device = "cuda"
    precision = torch.bfloat16
    checkpoint = Path(request.get("checkpoint", "checkpoints/s2-pro"))
    max_length = int(request.get("max_length", 4096))
    max_new_tokens = int(request.get("max_new_tokens", 512))
    if max_length < 4096 or not 2 <= max_new_tokens <= max_length - 2048:
        raise ValueError("Use a context of at least 4096 and a valid generation limit")
    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    prompt_text = request.get("reference_text")
    reference = request.get("reference")
    if bool(prompt_text) != bool(reference):
        raise ValueError("Reference audio and its transcript must be supplied together")
    prompt_tokens = None
    if reference:
        codec = load_codec_model(checkpoint / "codec.pth", device, precision)
        prompt_tokens = [encode_audio(reference, codec, device).cpu()]
        del codec
        gc.collect()
        torch.cuda.empty_cache()
    # Avoid transient FP32 initialization of a 4B model in system RAM.
    original_dtype = torch.get_default_dtype()
    try:
        torch.set_default_dtype(precision)
        model = DualARTransformer.from_pretrained(
            checkpoint, load_weights=True, max_length=max_length)
    finally:
        torch.set_default_dtype(original_dtype)
    model = model.to(device=device, dtype=precision).eval()
    load_seconds = time.perf_counter() - started
    samples = request.get("samples") or [{"text": request["text"], "output": request["output"]}]
    results = []
    for sample in samples:
        output = Path(sample["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        seed = int(sample.get("seed", request.get("seed", 42)))
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.cuda.synchronize()
        begin = time.perf_counter()
        chunks = []
        for response in generate_long(
            model=model, device=device, decode_one_token=decode_one_token_ar,
            text=sample["text"], max_new_tokens=max_new_tokens,
            top_p=float(request.get("top_p", 0.9)),
            temperature=float(request.get("temperature", 0.8)),
            prompt_text=[prompt_text] if prompt_text else None,
            prompt_tokens=prompt_tokens, compile=False,
        ):
            if response.action == "sample":
                if response.codes.shape[1] >= max_new_tokens - 1:
                    raise RuntimeError("Generation reached the token limit; output may be truncated")
                chunks.append(response.codes.cpu())
        torch.cuda.synchronize()
        codes = torch.cat(chunks, dim=1)
        np.save(output.with_suffix(".npy"), codes.numpy())
        results.append({"text": sample["text"], "output": str(output), "seed": seed,
                        "tokens": codes.shape[1],
                        "generate_seconds": time.perf_counter() - begin})
        del chunks, codes, response
    del model
    gc.collect()
    torch.cuda.empty_cache()
    codec = load_codec_model(checkpoint / "codec.pth", device, precision)
    for result in results:
        begin = time.perf_counter()
        codes = torch.from_numpy(np.load(Path(result["output"]).with_suffix(".npy"))).to(device)
        with torch.inference_mode():
            wave = decode_to_audio(codes, codec).float().cpu().numpy()
        if wave.size == 0 or not np.isfinite(wave).all() or np.max(np.abs(wave)) < 1e-4:
            raise RuntimeError("Invalid or silent audio")
        sf.write(result["output"], wave, codec.sample_rate, subtype="PCM_16")
        result.update(sample_rate=codec.sample_rate, audio_seconds=len(wave) / codec.sample_rate,
                      decode_seconds=time.perf_counter() - begin,
                      peak_amplitude=float(np.max(np.abs(wave))),
                      rms=float(np.sqrt(np.mean(wave ** 2))),
                      clipped_fraction=float(np.mean(np.abs(wave) >= 1)))
        result["rtf"] = (result["generate_seconds"] + result["decode_seconds"]) / result["audio_seconds"]
    report = {"model": "fishaudio/s2-pro", "precision": "bfloat16", "compile": False,
              "max_length": max_length, "max_new_tokens": max_new_tokens,
              "reference": reference, "reference_text": prompt_text,
              "load_seconds": load_seconds, "total_seconds": time.perf_counter() - started,
              "peak_allocated_gib": torch.cuda.max_memory_allocated() / 1024 ** 3,
              "peak_reserved_gib": torch.cuda.max_memory_reserved() / 1024 ** 3,
              "torch": torch.__version__, "gpu": torch.cuda.get_device_name(), "samples": results}
    report_path = Path(request.get("report", str(Path(results[0]["output"]).with_suffix(".json"))))
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
