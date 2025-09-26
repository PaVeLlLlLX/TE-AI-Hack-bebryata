# srcs/app.py (обновленная версия)
import streamlit as st
import os
from dotenv import load_dotenv

load_dotenv()

from agents.ingestor_agent import IngestorAgent
from agents.scripter_agent import ScripterAgent
# Обновляем импорты для художника и верстальщика
from agents.artist_agent import load_artist_models, generate_panel_image
from agents.layout_agent import create_comic_page

st.set_page_config(layout="wide")
st.title("AI-конвертер документов в комиксы 📜➡️🖼️")

@st.cache_resource
def load_all_models():
    """Загружает ВСЕ тяжелые модели один раз и кэширует их."""
    print("Загрузка всех агентов и моделей...")
    ingestor = IngestorAgent()
    scripter = ScripterAgent()
    # Загружаем модели художника (SDXL Base + Refiner)
    artist_base, artist_refiner = load_artist_models()
    print("Все агенты и модели готовы.")
    return ingestor, scripter, artist_base, artist_refiner

ingestor_agent, scripter_agent, artist_base_pipeline, artist_refiner_pipeline = load_all_models()

# --- UI Sidebar ---
st.sidebar.header("Настройки комикса")
style_choice = st.sidebar.selectbox(
    "1. Выберите стиль комикса:",
    ("Американский комикс 80-х", "Современная манга", "Нуарный детектив", "Детская иллюстрация")
)
audience_choice = st.sidebar.selectbox(
    "2. Выберите целевую аудиторию:",
    ("Для детей 10 лет", "Для подростков", "Для взрослых экспертов")
)

STYLE_KEYWORDS = {
    "Американский комикс 80-х": (
        "80s american comic book panel, graphic novel art, character-focused shot, bold outlines, "
        "vibrant flat colors, halftone dots shading"
    ),
    "Современная манга": (
        "modern manga panel, black and white, clean sharp line art, screentones shading, "
        "dynamic composition focused on characters, anime aesthetic"
    ),
    "Нуарный детектив": (
        "cinematic shot in a noir comic book style, film noir aesthetic, black and white, high contrast, "
        "dramatic shadows, focused on characters"
    ),
    "Детская иллюстрация": (
        "charming children's book illustration, cute cartoon style, simple rounded characters, "
        "soft lines, bright and friendly pastel colors"
    )
}

# --- Main UI ---
uploaded_file = st.file_uploader("Загрузите ваш PDF документ", type="pdf")
temp_pdf_path = "temp_uploaded_file.pdf"

if uploaded_file is not None:
    with open(temp_pdf_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    if st.button("✨ Создать комикс!"):
        # Шаги 1 и 2 остаются без изменений
        with st.spinner("Шаг 1/4: Читаю и распознаю документ..."):
            document_text = ingestor_agent.process_pdf(temp_pdf_path)
        st.success("Документ успешно прочитан!")
        
        with st.spinner("Шаг 2/4: Анализирую текст и пишу сценарий..."):
            scenario = scripter_agent.generate_script(document_text, style_choice, audience_choice)
        st.success("Сценарий готов!")
        
        with st.expander("Посмотреть сгенерированный JSON сценария"):
            st.json(scenario)

        # --- ОБНОВЛЕННЫЕ ШАГИ 3 и 4 ---
        if scenario and scenario.get("scenes"):
            images = []
            progress_bar = st.progress(0, text="Шаг 3/4: Рисую кадры...")
            num_scenes = len(scenario["scenes"])
            
            for i, scene in enumerate(scenario["scenes"]):
                status_text = f"Шаг 3/4: Рисую кадр {i+1}/{num_scenes}... 🎨"
                progress_bar.progress((i + 1) / num_scenes, text=status_text)
                
                image_prompt = scene["image_prompt"]
                style_keywords = STYLE_KEYWORDS.get(style_choice, "comic book style")
                
                # Вызываем обновленного художника, передавая ему загруженные модели
                generated_image = generate_panel_image(
                    base_pipeline=artist_base_pipeline,
                    refiner_pipeline=artist_refiner_pipeline,
                    image_prompt=image_prompt,
                    style_keywords=style_keywords
                )
                images.append(generated_image)
            
            st.success("Все кадры нарисованы!")

            with st.spinner("Шаг 4/4: Собираю страницу комикса... 📰"):
                # Layout agent уже должен быть готов и работать
                final_comic_page = create_comic_page(scenario, images, style_choice)
            st.success("Комикс готов!")
            
            st.image(final_comic_page, caption=f"Ваш комикс в стиле '{style_choice}'!", use_column_width=True)
            
            final_comic_page.save("output_comic.png")
            with open("output_comic.png", "rb") as file:
                st.download_button(
                    label="📥 Скачать комикс",
                    data=file,
                    file_name="my_comic.png",
                    mime="image/png"
                )
        else:
            st.error("Не удалось сгенерировать сценарий. Попробуйте другой документ.")

    if os.path.exists(temp_pdf_path):
        os.remove(temp_pdf_path)