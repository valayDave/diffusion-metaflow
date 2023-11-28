import os
import tempfile
from typing import List
from config import VideoGenerationConfig, VideoModelConfig

VIDEO_MODEL_ORG = "stabilityai"
VIDEO_MODEL_NAME = "stable-video-diffusion-img2vid"
VIDEO_MODEL_PATH = "./video-models"


def download_model(model_path=VIDEO_MODEL_PATH):
    from huggingface_hub import hf_hub_download

    hf_hub_download(
        repo_id=f"{VIDEO_MODEL_ORG}/{VIDEO_MODEL_NAME}",
        filename="svd.safetensors",
        local_dir=model_path,
        local_dir_use_symlinks=False,
    )


class ImageToVideo:
    @classmethod
    def generate(
        cls,
        model_version,
        image_paths: List[str],
        generation_config: VideoGenerationConfig,
        seed,
    ):
        from stability_gen_models.simple_sample_video import (
            sample as sample_images_to_video,
        )
        import torch

        for image_path in image_paths:
            with tempfile.TemporaryDirectory() as _dir:
                video_files = sample_images_to_video(
                    input_path=image_path,
                    num_frames=generation_config.num_frames,
                    num_steps=generation_config.num_steps,
                    version=model_version,
                    fps_id=generation_config.frame_rate,
                    motion_bucket_id=generation_config.motion_bucket_id,
                    seed=seed,
                    decoding_t=generation_config.decoding_timesteps,
                    device="cuda" if torch.cuda.is_available() else "cpu",
                    output_folder=_dir,
                    low_vram_mode=generation_config.low_vram_mode,
                )
                video_file = video_files[0]
                yield file_to_bytes(image_path), file_to_bytes(video_file)


def file_to_bytes(path):
    with open(path, "rb") as f:
        return f.read()
