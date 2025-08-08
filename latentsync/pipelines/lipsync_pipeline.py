# Adapted from https://github.com/guoyww/AnimateDiff/blob/main/animatediff/pipelines/pipeline_animation.py

import inspect
import math
import os
import shutil
from typing import Callable, List, Optional, Union, Dict, Any
import subprocess
from dataclasses import dataclass

import numpy as np
import torch
import torchvision
from torchvision import transforms

from packaging import version

from diffusers.configuration_utils import FrozenDict
from diffusers.models import AutoencoderKL
from diffusers.pipelines import DiffusionPipeline
from diffusers.schedulers import (
    DDIMScheduler,
    DPMSolverMultistepScheduler,
    EulerAncestralDiscreteScheduler,
    EulerDiscreteScheduler,
    LMSDiscreteScheduler,
    PNDMScheduler,
)
from diffusers.utils import deprecate

from einops import rearrange
import cv2

from ..models.unet import UNet3DConditionModel
from ..utils.util import read_video, read_audio, write_video, check_ffmpeg_installed
from ..utils.image_processor import ImageProcessor, load_fixed_mask
from ..utils.resample import resample_video_fps, resample_audio_sr
from ..utils.logger_config import setup_diffusers_logger
from ..whisper.audio2feature import Audio2Feature
import tqdm
import soundfile as sf

logger = setup_diffusers_logger(
    logger_name="lipsync_pipeline",
    to_console=False,
    to_file=True,
)

@dataclass
class ProcessingContext:
    """Context for processing, including all parameters equired during processing"""
    height: int
    width: int
    device: torch.device
    weight_dtype: torch.dtype
    do_classifier_free_guidance: bool
    generator: Optional[torch.Generator]
    timesteps: torch.Tensor
    extra_step_kwargs: Dict[str, Any]
    num_inference_steps: int
    guidance_scale: float
    callback: Optional[Callable]
    callback_steps: int

class LipsyncPipeline(DiffusionPipeline):
    _optional_components = []

    def __init__(
        self,
        vae: AutoencoderKL,
        audio_encoder: Audio2Feature,
        unet: UNet3DConditionModel,
        scheduler: Union[
            DDIMScheduler,
            PNDMScheduler,
            LMSDiscreteScheduler,
            EulerDiscreteScheduler,
            EulerAncestralDiscreteScheduler,
            DPMSolverMultistepScheduler,
        ],
    ):
        super().__init__()

        self._handle_scheduler_compatibility(scheduler)
        
        self._handle_unet_compatibility(unet)

        self.register_modules(
            vae=vae,
            audio_encoder=audio_encoder,
            unet=unet,
            scheduler=scheduler,
        )

        self.vae_scale_factor = 2 ** (len(self.vae.config.block_out_channels) - 1)

        self.set_progress_bar_config(desc="Steps")
    
    def _handle_scheduler_compatibility(self, scheduler):
        """Handle scheduler compatibility issues"""
        if hasattr(scheduler.config, "steps_offset") and scheduler.config.steps_offset != 1:
            deprecation_message = (
                f"The configuration file of this scheduler: {scheduler} is outdated. `steps_offset`"
                f" should be set to 1 instead of {scheduler.config.steps_offset}. Please make sure "
                "to update the config accordingly as leaving `steps_offset` might led to incorrect results"
                " in future versions. If you have downloaded this checkpoint from the Hugging Face Hub,"
                " it would be very nice if you could open a Pull request for the `scheduler/scheduler_config.json`"
                " file"
            )
            deprecate("steps_offset!=1", "1.0.0", deprecation_message, standard_warn=False)
            new_config = dict(scheduler.config)
            new_config["steps_offset"] = 1
            scheduler._internal_dict = FrozenDict(new_config)

        if hasattr(scheduler.config, "clip_sample") and scheduler.config.clip_sample is True:
            deprecation_message = (
                f"The configuration file of this scheduler: {scheduler} has not set the configuration `clip_sample`."
                " `clip_sample` should be set to False in the configuration file. Please make sure to update the"
                " config accordingly as not setting `clip_sample` in the config might lead to incorrect results in"
                " future versions. If you have downloaded this checkpoint from the Hugging Face Hub, it would be very"
                " nice if you could open a Pull request for the `scheduler/scheduler_config.json` file"
            )
            deprecate("clip_sample not set", "1.0.0", deprecation_message, standard_warn=False)
            new_config = dict(scheduler.config)
            new_config["clip_sample"] = False
            scheduler._internal_dict = FrozenDict(new_config)

    def _handle_unet_compatibility(self, unet):
        """Handle UNet compatibility issues"""
        is_unet_version_less_0_9_0 = hasattr(unet.config, "_diffusers_version") and version.parse(
            version.parse(unet.config._diffusers_version).base_version
        ) < version.parse("0.9.0.dev0")
        is_unet_sample_size_less_64 = hasattr(unet.config, "sample_size") and unet.config.sample_size < 64
        if is_unet_version_less_0_9_0 and is_unet_sample_size_less_64:
            deprecation_message = (
                "The configuration file of the unet has set the default `sample_size` to smaller than"
                " 64 which seems highly unlikely. If your checkpoint is a fine-tuned version of any of the"
                " following: \n- CompVis/stable-diffusion-v1-4 \n- CompVis/stable-diffusion-v1-3 \n-"
                " CompVis/stable-diffusion-v1-2 \n- CompVis/stable-diffusion-v1-1 \n- runwayml/stable-diffusion-v1-5"
                " \n- runwayml/stable-diffusion-inpainting \n you should change 'sample_size' to 64 in the"
                " configuration file. Please make sure to update the config accordingly as leaving `sample_size=32`"
                " in the config might lead to incorrect results in future versions. If you have downloaded this"
                " checkpoint from the Hugging Face Hub, it would be very nice if you could open a Pull request for"
                " the `unet/config.json` file"
            )
            deprecate("sample_size<64", "1.0.0", deprecation_message, standard_warn=False)
            new_config = dict(unet.config)
            new_config["sample_size"] = 64
            unet._internal_dict = FrozenDict(new_config)

    def enable_vae_slicing(self):
        self.vae.enable_slicing()

    def disable_vae_slicing(self):
        self.vae.disable_slicing()

    @property
    def _execution_device(self):
        if self.device != torch.device("meta") or not hasattr(self.unet, "_hf_hook"):
            return self.device
        for module in self.unet.modules():
            if (
                hasattr(module, "_hf_hook")
                and hasattr(module._hf_hook, "execution_device")
                and module._hf_hook.execution_device is not None
            ):
                return torch.device(module._hf_hook.execution_device)
        return self.device

    def decode_latents(self, latents):
        latents = latents / self.vae.config.scaling_factor + self.vae.config.shift_factor
        latents = rearrange(latents, "b c f h w -> (b f) c h w")
        decoded_latents = self.vae.decode(latents).sample
        return decoded_latents

    def prepare_extra_step_kwargs(self, generator, eta):
        # prepare extra kwargs for the scheduler step, since not all schedulers have the same signature
        # eta (η) is only used with the DDIMScheduler, it will be ignored for other schedulers.
        # eta corresponds to η in DDIM paper: https://arxiv.org/abs/2010.02502
        # and should be between [0, 1]

        accepts_eta = "eta" in set(inspect.signature(self.scheduler.step).parameters.keys())
        extra_step_kwargs = {}
        if accepts_eta:
            extra_step_kwargs["eta"] = eta

        # check if the scheduler accepts generator
        accepts_generator = "generator" in set(inspect.signature(self.scheduler.step).parameters.keys())
        if accepts_generator:
            extra_step_kwargs["generator"] = generator
        return extra_step_kwargs

    def check_inputs(self, height, width, callback_steps):
        assert height == width, "Height and width must be equal"

        if height % 8 != 0 or width % 8 != 0:
            raise ValueError(f"`height` and `width` have to be divisible by 8 but are {height} and {width}.")

        if (callback_steps is None) or (
            callback_steps is not None and (not isinstance(callback_steps, int) or callback_steps <= 0)
        ):
            raise ValueError(
                f"`callback_steps` has to be a positive integer but is {callback_steps} of type"
                f" {type(callback_steps)}."
            )

    def prepare_latents(self, num_frames, num_channels_latents, height, width, dtype, device, generator):
        shape = (
            1,
            num_channels_latents,
            1,
            height // self.vae_scale_factor,
            width // self.vae_scale_factor,
        )  # (b, c, f, h, w)
        rand_device = "cpu" if device.type == "mps" else device
        latents = torch.randn(shape, generator=generator, device=rand_device, dtype=dtype).to(device)
        latents = latents.repeat(1, 1, num_frames, 1, 1)

        # scale the initial noise by the standard deviation required by the scheduler
        latents = latents * self.scheduler.init_noise_sigma
        return latents

    def prepare_mask_latents(
        self, mask, masked_image, height, width, dtype, device, generator, do_classifier_free_guidance
    ):
        # resize the mask to latents shape as we concatenate the mask to the latents
        # we do that before converting to dtype to avoid breaking in case we're using cpu_offload
        # and half precision
        mask = torch.nn.functional.interpolate(
            mask, size=(height // self.vae_scale_factor, width // self.vae_scale_factor)
        )
        masked_image = masked_image.to(device=device, dtype=dtype)

        # encode the mask image into latents space so we can concatenate it to the latents
        masked_image_latents = self.vae.encode(masked_image).latent_dist.sample(generator=generator)
        masked_image_latents = (masked_image_latents - self.vae.config.shift_factor) * self.vae.config.scaling_factor

        # aligning device to prevent device errors when concating it with the latent model input
        masked_image_latents = masked_image_latents.to(device=device, dtype=dtype)
        mask = mask.to(device=device, dtype=dtype)

        # assume batch size = 1
        mask = rearrange(mask, "f c h w -> 1 c f h w")
        masked_image_latents = rearrange(masked_image_latents, "f c h w -> 1 c f h w")

        mask = torch.cat([mask] * 2) if do_classifier_free_guidance else mask
        masked_image_latents = (
            torch.cat([masked_image_latents] * 2) if do_classifier_free_guidance else masked_image_latents
        )
        return mask, masked_image_latents

    def prepare_image_latents(self, images, device, dtype, generator, do_classifier_free_guidance):
        images = images.to(device=device, dtype=dtype)
        image_latents = self.vae.encode(images).latent_dist.sample(generator=generator)
        image_latents = (image_latents - self.vae.config.shift_factor) * self.vae.config.scaling_factor
        image_latents = rearrange(image_latents, "f c h w -> 1 c f h w")
        image_latents = torch.cat([image_latents] * 2) if do_classifier_free_guidance else image_latents

        return image_latents

    def set_progress_bar_config(self, **kwargs):
        if not hasattr(self, "_progress_bar_config"):
            self._progress_bar_config = {}
        self._progress_bar_config.update(kwargs)

    @staticmethod
    def paste_surrounding_pixels_back(decoded_latents, pixel_values, masks, device, weight_dtype):
        # Paste the surrounding pixels back, because we only want to change the mouth region
        pixel_values = pixel_values.to(device=device, dtype=weight_dtype)
        masks = masks.to(device=device, dtype=weight_dtype)
        combined_pixel_values = decoded_latents * masks + pixel_values * (1 - masks)
        return combined_pixel_values

    @staticmethod
    def pixel_values_to_images(pixel_values: torch.Tensor):
        pixel_values = rearrange(pixel_values, "f c h w -> f h w c")
        pixel_values = (pixel_values / 2 + 0.5).clamp(0, 1)
        images = (pixel_values * 255).to(torch.uint8)
        images = images.cpu().numpy()
        return images

    def affine_transform_video(self, video_frames: np.ndarray):
        faces = []
        boxes = []
        affine_matrices = []
        has_face_flags = []  # Marks each frame with or without face
        for idx, frame in enumerate(tqdm.tqdm(video_frames, desc="Affine transforming faces")):
            try:
                face, box, affine_matrix = self.image_processor.affine_transform(frame)
                faces.append(face)
                boxes.append(box)
                affine_matrices.append(affine_matrix)
                has_face_flags.append(True)
            except RuntimeError as e:
                if "Face not detected" in str(e):
                    logger.warning(f"Frame {idx}: Face not detected. Using placeholder.")
                    placeholder_face = torch.full(
                        (
                            3, 
                            self.image_processor.resolution, 
                            self.image_processor.resolution
                        ),
                        127.0   # Medium gray
                    )
                    faces.append(placeholder_face)
                    boxes.append(None)
                    affine_matrices.append(None)
                    has_face_flags.append(False)
                else:
                    raise e

        faces = torch.stack(faces)
        return faces, boxes, affine_matrices, has_face_flags

    def restore_video(self, faces: torch.Tensor, video_frames: np.ndarray, boxes: list, affine_matrices: list, has_face_flags: list):
        video_frames = video_frames[: len(faces)]
        out_frames = []
        print(f"Restoring {len(faces)} faces...")
        for index, face in enumerate(tqdm.tqdm(faces)):
            # If there is no face in the current frame, use the original frame directly
            if not has_face_flags[index]:
                out_frames.append(video_frames[index])
                continue
            x1, y1, x2, y2 = boxes[index]
            height = int(y2 - y1)
            width = int(x2 - x1)
            face = torchvision.transforms.functional.resize(
                face, size=(height, width), interpolation=transforms.InterpolationMode.BICUBIC, antialias=True
            )
            out_frame = self.image_processor.restorer.restore_img(video_frames[index], face, affine_matrices[index])
            out_frames.append(out_frame)
        return np.stack(out_frames, axis=0)

    def loop_video(self, whisper_chunks: list, video_frames: np.ndarray):
        # If the audio is longer than the video, we need to loop the video
        if len(whisper_chunks) > len(video_frames):
            # Use index mapping to create data after the loop to avoid memory copying
            num_original_frames = len(video_frames)
            num_required_frames = len(whisper_chunks)
            num_loops = math.ceil(num_required_frames / num_original_frames)

            # Create frame index map
            frame_indices = []
            for i in range(num_loops):
                if i % 2 == 0:
                    # Play forward
                    indices = list(range(num_original_frames))
                else:
                    # Play reverse
                    indices = list(range(num_original_frames - 1, -1, -1))
                frame_indices.extend(indices)
            
            frame_indices = frame_indices[:num_required_frames]
            looped_video_frames = video_frames[frame_indices]
            
            return looped_video_frames
        else:
            video_frames = video_frames[: len(whisper_chunks)]
            return video_frames

    def analyze_chunk(self, has_face_flags):
        """Analyze the type of chunk：pure_face, pure_no_face, binary_mixed, complex_mixed"""
        face_count = sum(has_face_flags)
        total_count = len(has_face_flags)
        
        if face_count == 0:
            return "pure_no_face", None
        elif face_count == total_count:
            return "pure_face", None
        else:
            # check if it can be split into two parts
            transitions = []
            for i in range(1, len(has_face_flags)):
                if has_face_flags[i] != has_face_flags[i - 1]:
                    transitions.append(i)
            
            if len(transitions) == 1:
                # can be split into two parts
                return "binary_mixed", transitions[0]
            else:
                # complex mixed
                return "complex_mixed", transitions
    
    def process_chunk(
        self, 
        chunk_start: int, 
        chunk_end: int, 
        whisper_chunk: List, 
        video_frame_chunk: np.ndarray,
        latent_chunk: torch.Tensor, 
        context: ProcessingContext
    ):
        """Process chunk and return results with metadata"""
        chunk_faces, chunk_boxes, chunk_affine_matrices, chunk_has_face_flags = self.affine_transform_video(video_frame_chunk)

        chunk_type, split_info = self.analyze_chunk(chunk_has_face_flags)
        
        if chunk_type == "pure_no_face":
            # pure no face chunk, do not execute lipsync
            logger.info(f"Chunk [{chunk_start}:{chunk_end}]: No faces detected, adding placeholders")
            result = self._process_pure_no_face_chunk(
                chunk_length=len(whisper_chunk),
                context=context
            )
            return [result], chunk_boxes, chunk_affine_matrices, chunk_has_face_flags
        
        elif chunk_type == 'pure_face':
            # pure face chunk, execute lipsync
            result = self._process_face_chunk(
                whisper_chunk, chunk_faces, latent_chunk, context
            )
            return [result], chunk_boxes, chunk_affine_matrices, chunk_has_face_flags
        
        elif chunk_type == 'binary_mixed':
            # binary mixed chunk: split into two parts and process them separately
            logger.warning(f"Chunk [{chunk_start}:{chunk_end}]: Binary mixed, splitting at position {split_info + chunk_start}")
            result = self._process_binary_mixed_chunk(
                whisper_chunk, chunk_faces, latent_chunk, chunk_has_face_flags, split_info, context
            )
            return result, chunk_boxes, chunk_affine_matrices, chunk_has_face_flags
        
        else:  # complex_mixed
            # complex mixed chunk, warning and process as a whole chunk
            logger.warning(f"Chunk [{chunk_start}:{chunk_end}]: Complex mixed pattern detected!")
            logger.warning(f"  Pattern: {chunk_has_face_flags}")
            logger.warning(f"  Transitions at: {split_info}")
            logger.warning(f"  Processing as a whole chunk (may affect quality)")
            
            result = self._process_face_chunk(
                whisper_chunk, chunk_faces, latent_chunk, context
            )
            return [result], chunk_boxes, chunk_affine_matrices, chunk_has_face_flags

    def _process_pure_no_face_chunk(
        self,
        chunk_length: int,
        context: ProcessingContext
    ):
        placeholder_frames = torch.full(
            (chunk_length, 3, context.height, context.width),
            0.0,
            device=context.device,
            dtype=context.weight_dtype
        )
        return placeholder_frames

    def _process_face_chunk(
        self, 
        whisper_chunk: List, 
        inference_faces: torch.Tensor, 
        latents: torch.Tensor, 
        context: ProcessingContext
    ):
        """Process chunk with face"""

        height = context.height
        width = context.width
        device = context.device
        weight_dtype = context.weight_dtype
        do_classifier_free_guidance = context.do_classifier_free_guidance
        generator = context.generator
        timesteps = context.timesteps
        extra_step_kwargs = context.extra_step_kwargs
        num_inference_steps = context.num_inference_steps
        guidance_scale = context.guidance_scale
        callback = context.callback
        callback_steps = context.callback_steps

        # prepare audio embeds
        if self.unet.add_audio_layer:
            audio_embeds = torch.stack(whisper_chunk)
            audio_embeds = audio_embeds.to(device, dtype=weight_dtype)
            if do_classifier_free_guidance:
                null_audio_embeds = torch.zeros_like(audio_embeds)
                audio_embeds = torch.cat([null_audio_embeds, audio_embeds])
        else:
            audio_embeds = None
        
        ref_pixel_values, masked_pixel_values, masks = self.image_processor.prepare_masks_and_masked_images(
            inference_faces, affine_transform=False
        )
        
        # Prepare mask latent variables
        mask_latents, masked_image_latents = self.prepare_mask_latents(
            masks,
            masked_pixel_values,
            height,
            width,
            weight_dtype,
            device,
            generator,
            do_classifier_free_guidance,
        )
        
        # Prepare image latents
        ref_latents = self.prepare_image_latents(
            ref_pixel_values,
            device,
            weight_dtype,
            generator,
            do_classifier_free_guidance,
        )
        
        # Denoising loop
        num_warmup_steps = len(timesteps) - num_inference_steps * self.scheduler.order
        with self.progress_bar(total=num_inference_steps) as progress_bar:
            for j, t in enumerate(timesteps):
                unet_input = torch.cat([latents] * 2) if do_classifier_free_guidance else latents
                unet_input = self.scheduler.scale_model_input(unet_input, t)
                unet_input = torch.cat([unet_input, mask_latents, masked_image_latents, ref_latents], dim=1)
                
                noise_pred = self.unet(unet_input, t, encoder_hidden_states=audio_embeds).sample
                
                if do_classifier_free_guidance:
                    noise_pred_uncond, noise_pred_audio = noise_pred.chunk(2)
                    noise_pred = noise_pred_uncond + guidance_scale * (noise_pred_audio - noise_pred_uncond)
                
                latents = self.scheduler.step(noise_pred, t, latents, **extra_step_kwargs).prev_sample
                
                if j == len(timesteps) - 1 or ((j + 1) > num_warmup_steps and (j + 1) % self.scheduler.order == 0):
                    progress_bar.update()
                    if callback is not None and j % callback_steps == 0:
                        callback(j, t, latents)
        
        # Decode latents
        decoded_latents = self.decode_latents(latents)
        decoded_latents = self.paste_surrounding_pixels_back(
            decoded_latents, ref_pixel_values, 1 - masks, device, weight_dtype
        )
        
        return decoded_latents

    def _process_binary_mixed_chunk(
        self,
        whisper_chunk: List,
        chunk_faces: torch.Tensor,
        latent_chunk: torch.Tensor,
        chunk_has_face_flags: List[bool],
        split_point: int,
        context: ProcessingContext
    ):
        # process the first part
        if chunk_has_face_flags[0]:  # the first part has face
            result1 = self._process_face_chunk(
                whisper_chunk[:split_point], 
                chunk_faces[:split_point], 
                latent_chunk[:, :, :split_point], 
                context
            )
            result2 = self._process_pure_no_face_chunk(
                chunk_length=len(whisper_chunk) - split_point,
                context=context
            )
        else:  # the first part has no face
            result1 = self._process_pure_no_face_chunk(
                chunk_length=split_point,
                context=context
            )
            result2 = self._process_face_chunk(
                whisper_chunk[split_point:], 
                chunk_faces[split_point:], 
                latent_chunk[:, :, split_point:], 
                context
            )
        
        return [result1, result2]

    
    @torch.no_grad()
    def __call__(
        self,
        video_path: str,
        audio_path: str,
        video_out_path: str,
        num_frames: int = 16,
        video_fps: int = 25,
        audio_sample_rate: int = 16000,
        height: Optional[int] = None,
        width: Optional[int] = None,
        num_inference_steps: int = 20,
        guidance_scale: float = 1.5,
        weight_dtype: Optional[torch.dtype] = torch.float16,
        eta: float = 0.0,
        mask_image_path: str = "latentsync/utils/mask.png",
        temp_dir: str = "temp",
        generator: Optional[Union[torch.Generator, List[torch.Generator]]] = None,
        callback: Optional[Callable[[int, int, torch.FloatTensor], None]] = None,
        callback_steps: Optional[int] = 1,
        **kwargs,
    ):
        is_train = self.unet.training
        self.unet.eval()

        check_ffmpeg_installed()

        # resample video and audio
        video_path = resample_video_fps(
            video_path, video_fps
        )
        audio_path = resample_audio_sr(
            audio_path, audio_sample_rate
        )

        # 0. Define call parameters
        device = self._execution_device
        mask_image = load_fixed_mask(height, mask_image_path)
        self.image_processor = ImageProcessor(height, device="cuda", mask_image=mask_image)
        self.set_progress_bar_config(desc=f"Sample frames: {num_frames}")

        # 1. Default height and width to unet
        height = height or self.unet.config.sample_size * self.vae_scale_factor
        width = width or self.unet.config.sample_size * self.vae_scale_factor

        # 2. Check inputs
        self.check_inputs(height, width, callback_steps)

        # here `guidance_scale` is defined analog to the guidance weight `w` of equation (2)
        # of the Imagen paper: https://arxiv.org/pdf/2205.11487.pdf . `guidance_scale = 1`
        # corresponds to doing no classifier free guidance.
        do_classifier_free_guidance = guidance_scale > 1.0

        # 3. set timesteps
        self.scheduler.set_timesteps(num_inference_steps, device=device)
        timesteps = self.scheduler.timesteps

        # 4. Prepare extra step kwargs.
        extra_step_kwargs = self.prepare_extra_step_kwargs(generator, eta)

        whisper_feature = self.audio_encoder.audio2feat(audio_path)
        whisper_chunks = self.audio_encoder.feature2chunks(feature_array=whisper_feature, fps=video_fps)

        audio_samples = read_audio(audio_path)
        video_frames = read_video(video_path, use_decord=False)

        video_frames = self.loop_video(whisper_chunks, video_frames)

        num_channels_latents = self.vae.config.latent_channels

        # Prepare latent variables
        all_latents = self.prepare_latents(
            len(whisper_chunks),
            num_channels_latents,
            height,
            width,
            weight_dtype,
            device,
            generator,
        )

        # 创建处理上下文
        context = ProcessingContext(
            height=height,
            width=width,
            device=device,
            weight_dtype=weight_dtype,
            do_classifier_free_guidance=do_classifier_free_guidance,
            generator=generator,
            timesteps=timesteps,
            extra_step_kwargs=extra_step_kwargs,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            callback=callback,
            callback_steps=callback_steps
        )

        synced_video_frames = []
        all_boxes = []
        all_affine_matrices = []
        all_has_face_flags = []

        num_inferences = math.ceil(len(whisper_chunks) / num_frames)
        for i in tqdm.tqdm(range(num_inferences), desc="Doing inference..."):
            logger.info(f"Processing chunk {i}...")

            chunk_start = i * num_frames
            chunk_end = min((i + 1) * num_frames, len(whisper_chunks))
            
            # process chunk
            decoded_latents, chunk_boxes, chunk_affine_matrices, chunk_has_face = self.process_chunk(
                chunk_start,
                chunk_end,
                whisper_chunk=whisper_chunks[chunk_start:chunk_end],
                video_frame_chunk=video_frames[chunk_start:chunk_end],
                latent_chunk=all_latents[:, :, chunk_start:chunk_end],
                context=context
            )
            
            synced_video_frames.extend(decoded_latents)
            all_boxes.extend(chunk_boxes)
            all_affine_matrices.extend(chunk_affine_matrices)
            all_has_face_flags.extend(chunk_has_face)
        
        synced_video_frames = self.restore_video(torch.cat(synced_video_frames), video_frames, all_boxes, all_affine_matrices, all_has_face_flags)

        audio_samples_remain_length = int(synced_video_frames.shape[0] / video_fps * audio_sample_rate)
        audio_samples = audio_samples[:audio_samples_remain_length].cpu().numpy()

        if is_train:
            self.unet.train()

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)

        write_video(os.path.join(temp_dir, "video.mp4"), synced_video_frames, fps=video_fps)

        sf.write(os.path.join(temp_dir, "audio.wav"), audio_samples, audio_sample_rate)

        command = f"ffmpeg -y -loglevel error -nostdin -i {os.path.join(temp_dir, 'video.mp4')} -i {os.path.join(temp_dir, 'audio.wav')} -c:v libx264 -crf 18 -c:a aac -q:v 0 -q:a 0 {video_out_path}"
        subprocess.run(command, shell=True)
