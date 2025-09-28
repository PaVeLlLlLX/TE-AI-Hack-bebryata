# srcs/app.py
import streamlit as st
import os
from dotenv import load_dotenv
from io import BytesIO

load_dotenv()

from agents.ingestor_agent import IngestorAgent
from agents.scripter_agent import ScripterAgent
from agents.artist_agent import load_artist_models, generate_panel_image
from agents.layout_agent import create_comic_page

st.set_page_config(layout="wide")
st.title("AI-конвертер документов в комиксы 📜➡️🖼️")

if 'comic_generated' not in st.session_state:
    st.session_state.comic_generated = False
if 'generated_pages' not in st.session_state:
    st.session_state.generated_pages = []

@st.cache_resource
def load_all_models():
    print("Загрузка всех агентов и клиентов..."); ingestor = IngestorAgent(); scripter = ScripterAgent(); artist_client = load_artist_models()
    print("Все агенты и клиенты готовы."); return ingestor, scripter, artist_client

ingestor_agent, scripter_agent, artist_client = load_all_models()

st.sidebar.header("Настройки комикса")
style_choice = st.sidebar.selectbox("1. Выберите стиль комикса:", ("Американский комикс 80-х", "Современная манга", "Нуарный детектив", "Детская иллюстрация"))
audience_choice = st.sidebar.selectbox("2. Выберите целевую аудиторию:", ("Для детей 10 лет", "Для подростков", "Для взрослых экспертов"))
max_pages_choice = st.sidebar.slider("3. Количество страниц:", min_value=1, max_value=5, value=3, help="Выберите, сколько тематических страниц комикса сгенерировать.")
consistent_chars = st.sidebar.checkbox("Единые персонажи для всего комикса", value=True, help="Если включено, AI придумает одних и тех же героев для всех страниц.")
STYLE_KEYWORDS = {
    "Американский комикс 80-х": "80s comic book art, character-focused, bold outlines, halftone shading",
    "Современная манга": "dynamic black and white manga art, clean sharp lines, screentone shading, character-focused",
    "Нуарный детектив": "cinematic noir comic art, high-contrast black and white, dramatic chiaroscuro lighting",
    "Детская иллюстрация": "charming children's book illustration, cute cartoon style, simple characters, pastel colors"
}

uploaded_file = st.file_uploader("Загрузите ваш PDF документ", type="pdf")
temp_pdf_path = "temp_uploaded_file.pdf"

if uploaded_file is not None:
    with open(temp_pdf_path, "wb") as f: f.write(uploaded_file.getbuffer())

    if st.button("✨ Создать комикс!", key="generate_button"):
        st.session_state.comic_generated = False
        st.session_state.generated_pages = []
        
        with st.spinner("Шаг 1/N: Читаю и распознаю документ..."):
            document_text = ingestor_agent.process_pdf(temp_pdf_path)
        st.success("Документ успешно прочитан!")
        
        with st.spinner("Шаг 2/N: Анализирую документ и пишу сценарии по темам..."):
            scenarios = scripter_agent.generate_themed_scripts(document_text, style_choice, audience_choice, max_pages=max_pages_choice, use_consistent_characters=consistent_chars)
            #scenarios = scripter_agent.generate_themed_scripts(document_text, max_pages=max_pages_choice)
        if not scenarios:
            st.error("Не удалось сгенерировать ни одного сценария.")
        else:
            st.success(f"Сценарии для {len(scenarios)} страниц комикса готовы!")
            
            all_pages_data = []
            for i, scenario in enumerate(scenarios):
                page_num = i + 1
                with st.spinner(f"Генерация страницы {page_num}/{len(scenarios)}: \"{scenario.get('title', '')}\"..."):
                    if scenario and scenario.get("scenes"):
                        images = []
                        for j, scene in enumerate(scenario["scenes"]):
                            style_keywords = STYLE_KEYWORDS.get(style_choice, "comic book style")
                            generated_image = generate_panel_image(client=artist_client, scene=scene, style_keywords=style_keywords)
                            images.append(generated_image)
                        final_comic_page = create_comic_page(scenario, images, style_choice)
                        page_filename = f"comic_page_{page_num}_{style_choice.replace(' ', '_')}.png"
                        all_pages_data.append((final_comic_page, page_filename))
            st.session_state.generated_pages = all_pages_data
            st.session_state.comic_generated = True


if st.session_state.comic_generated and st.session_state.generated_pages:
    st.markdown("---")
    st.header("Готовые комиксы:")
    
    for i, (page_image, page_filename) in enumerate(st.session_state.generated_pages):
        st.image(page_image, caption=f"Страница {i+1}", use_column_width=True)
        buf = BytesIO()
        page_image.save(buf, format="PNG")
        byte_im = buf.getvalue()
        st.download_button(
            label=f"📥 Скачать страницу {i+1}",
            data=byte_im,
            file_name=page_filename,
            mime="image/png",
            key=f"download_button_{i}"
        )
        st.markdown("---")

if os.path.exists(temp_pdf_path):
    os.remove(temp_pdf_path)