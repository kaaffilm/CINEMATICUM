from pathlib import Path
from huggingface_hub import hf_hub_download

root = Path("/Users/midiakiasat/Downloads/Apps/midiakiasat/Kaaffilm/CINEMATICUM/.runtime/ComfyUI")
repo = "Comfy-Org/Wan_2.1_ComfyUI_repackaged"

files = [
    ("split_files/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors", root / "models/diffusion_models"),
    ("split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", root / "models/text_encoders"),
    ("split_files/vae/wan_2.1_vae.safetensors", root / "models/vae"),
]

for filename, outdir in files:
    outdir.mkdir(parents=True, exist_ok=True)
    target = outdir / Path(filename).name
    if target.exists() and target.stat().st_size > 100_000_000:
        print(f"MODEL_PRESENT={target}")
        continue
    print(f"DOWNLOADING={filename}")
    path = hf_hub_download(
        repo_id=repo,
        filename=filename,
        local_dir=root,
        local_dir_use_symlinks=False,
    )
    print(f"DOWNLOADED={path}")

print("FREE_WAN21_T2V_13B_MODELS_READY=true")
