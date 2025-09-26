# agents/artist_agent.py

import torch
from diffusers import DiffusionPipeline
from PIL import Image
import streamlit as st
import gc # <-- ДОБАВЛЕНО: импортируем сборщик мусора

@st.cache_resource
def load_artist_models():
    """
    Загружает базовую модель SDXL и модель-улучшатель (Refiner).
    Включает оптимизации для экономии VRAM.
    """
    print("Загрузка моделей художника (SDXL Base + Refiner) с оптимизацией памяти...")
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # 1. Загрузка базовой модели
    base_pipeline = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True
    )
    # <-- ГЛАВНОЕ ИЗМЕНЕНИЕ: Включаем последовательную выгрузку в CPU -->
    # Это самый эффективный способ экономии памяти.
    # Модель будет держать на GPU только необходимые в данный момент компоненты.
    base_pipeline.enable_sequential_cpu_offload()

    # 2. Загрузка модели-улучшателя (Refiner)
    refiner_pipeline = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-refiner-1.0",
        text_encoder_2=base_pipeline.text_encoder_2,
        vae=base_pipeline.vae,
        torch_dtype=torch.float16,
        use_safetensors=True,
        variant="fp16",
    )
    # <-- Применяем ту же магию к Refiner -->
    refiner_pipeline.enable_sequential_cpu_offload()
    
    print("Модели художника успешно загружены.")
    return base_pipeline, refiner_pipeline


def generate_panel_image(
    base_pipeline: DiffusionPipeline, 
    refiner_pipeline: DiffusionPipeline, 
    image_prompt: str, 
    style_keywords: str
) -> Image.Image:
    """
    Генерирует изображение для одного кадра комикса, используя Base + Refiner.
    """
    full_prompt = f"{style_keywords}. An illustration of: {image_prompt}. masterpiece, detailed, high quality."
    
    # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: УСИЛЕННЫЙ НЕГАТИВНЫЙ ПРОМПТ ---
    # Добавляем все возможные слова, связанные с текстом, чтобы модель их избегала.
    negative_prompt = (
        "text, speech bubble, dialogue, writing, letters, font, signature, labels, words, " # <-- ЗАПРЕТ ТЕКСТА
        "photorealistic, photography, 3d render, architecture sketch, pattern, ornament, "
        "blurry, worst quality, low quality, deformed, ugly, "
        "extra limbs, disfigured, poorly drawn hands, poorly drawn face, empty scene"
    )
    
    print(f"Генерирую изображение с промптом: {full_prompt}")

    with torch.no_grad():
        latents = base_pipeline(
            prompt=full_prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=30,
            guidance_scale=8.0,
            output_type="latent",
        ).images
        
        image = refiner_pipeline(
            prompt=full_prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=20,
            strength=0.3,
            image=latents,
        ).images[0]
    
    torch.cuda.empty_cache()
    gc.collect()
    
    return image