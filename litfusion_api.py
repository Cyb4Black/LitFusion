import os
import json
from PIL import Image
from litserve import LitServer, LitAPI
from diffusers import AutoPipelineForText2Image, AutoPipelineForImage2Image, AutoPipelineForInpainting
import torch

from openai_image_spec import OpenAIImageSpec


class LitFusion(LitAPI):
    def __init__(self):
        self.pipeline = None
        self.quality_presets = None
        self.enable_image_variations = None
        self.enable_image_edits = None
        self.enable_images_generation = None
        self.enable_vae_tiling = None
        self.enable_vae_slicing = None
        self.enable_cpu_offload = None
        self.max_n = None
        self.model_name = None

    def setup(self, device):
        # Load model and configuration from environment variables and config.json
        self.model_name = os.getenv("MODEL", "default-model")
        self.max_n = int(os.getenv("MAX_N", 10))
        self.enable_cpu_offload = bool(int(os.getenv("ENABLE_CPU_OFFLOAD", 0)))
        self.enable_vae_slicing = bool(int(os.getenv("ENABLE_VAE_SLICING", 0)))
        self.enable_vae_tiling = bool(int(os.getenv("ENABLE_VAE_TILING", 0)))

        # Load feature enabling flags from environment variables
        self.enable_images_generation = bool(int(os.getenv("ENABLE_IMAGES_GENERATION", 1)))
        self.enable_image_edits = bool(int(os.getenv("ENABLE_IMAGE_EDITS", 1)))
        self.enable_image_variations = bool(int(os.getenv("ENABLE_IMAGE_VARIATIONS", 1)))

        # Load configuration JSON
        config_path = "config.json"
        if os.path.exists(config_path):
            with open(config_path, "r") as config_file:
                self.quality_presets = json.load(config_file)
        else:
            self.quality_presets = {}
        
        # Load the model pipeline using AutoPipelineForText2Image
        print("Loading model pipeline...")
        if self.enable_images_generation:
            self.pipeline = AutoPipelineForText2Image.from_pretrained(self.model_name, torch_dtype=torch.bfloat16)
        elif self.enable_image_edits:
            self.pipeline = AutoPipelineForInpainting.from_pretrained(self.model_name, torch_dtype=torch.bfloat16)
        elif self.enable_image_variations:
            self.pipeline = AutoPipelineForImage2Image.from_pretrained(self.model_name, torch_dtype=torch.bfloat16)
        else:
            raise ValueError("No pipeline enabled. Please enable at least one of the following: images generation, image edits, image variations")

        # Apply settings before moving to GPU if necessary
        if self.enable_cpu_offload:
            self.pipeline.enable_sequential_cpu_offload()
        if self.enable_vae_slicing:
            self.pipeline.vae.enable_slicing()
        if self.enable_vae_tiling:
            self.pipeline.vae.enable_tiling()

        # Move the pipeline to GPU and convert to float16
        self.pipeline.to(torch.float16).to("cuda")
        
        print("Model setup complete with:")
        print(f"Model: {self.model_name}")
        print(f"Max value for n: {self.max_n}")
        print(f"CPU Offload Enabled: {self.enable_cpu_offload}")
        print(f"VAE Slicing Enabled: {self.enable_vae_slicing}")
        print(f"VAE Tiling Enabled: {self.enable_vae_tiling}")
        print(f"Images Generation Enabled: {self.enable_images_generation}")
        print(f"Image Edits Enabled: {self.enable_image_edits}")
        print(f"Image Variations Enabled: {self.enable_image_variations}")

    def predict(self, request):
        # Logic to determine which type of request it is
        request_type = request.get('request_type')
        if request_type == "generation" and self.enable_images_generation:
            yield self.generate_images(request)
        elif request_type == "edit" and self.enable_image_edits:
            yield self.edit_images(request)
        elif request_type == "variation" and self.enable_image_variations:
            yield self.generate_variations(request)
        else:
            yield "Unknown or disabled request type"

    def generate_images(self, request):
        gen_pipe = AutoPipelineForText2Image.from_pipe(self.pipeline)
        for _ in range(min(request.get('n', 1), self.max_n)):
            prompt = request.get('prompt', 'A beautiful landscape')
            images = gen_pipe(prompt=prompt).images
            for img in images:
                yield img

    def edit_images(self, request):
        edit_pipe = AutoPipelineForInpainting.from_pipe(self.pipeline)
        for _ in range(min(request.get('n', 1), self.max_n)):
            prompt = request.get('prompt', 'Edit the image to look more vibrant')
            init_image = request.get('image')
            mask_image = request.get('mask')
            images = edit_pipe(prompt=prompt, image=init_image, mask_image=mask_image).images
            for img in images:
                yield img

    def generate_variations(self, request):
        var_pipe = AutoPipelineForImage2Image.from_pipe(self.pipeline)
        for _ in range(min(request.get('n', 1), self.max_n)):
            prompt = request.get('prompt', 'Generate variations')
            init_image = request.get('image')
            images = var_pipe(prompt=prompt, image=init_image).images
            for img in images:
                yield img


api = LitFusion()
server = LitServer(api, spec=OpenAIImageSpec())
server.run(port=8000)
