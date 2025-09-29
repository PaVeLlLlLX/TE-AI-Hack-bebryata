import streamlit as st
import os
from dotenv import load_dotenv
from io import BytesIO

load_dotenv()
from agents.ingestor_agent import IngestorAgent
from agents.scripter_agent import ScripterAgent
from agents.artist_agent import load_artist_models, generate_all_panels_in_parallel, generate_panel_image
from agents.layout_agent import create_comic_page

st.set_page_config(layout="wide", page_title="AI Comics Converter")

if 'generation_complete' not in st.session_state:
    st.session_state.generation_complete = False
if 'editor_data' not in st.session_state:
    st.session_state.editor_data = []
if 'final_pages' not in st.session_state:
    st.session_state.final_pages = []

@st.cache_resource
def load_all_models():
    print("Загрузка всех агентов и клиентов...")
    ingestor = IngestorAgent()
    scripter = ScripterAgent()
    artist_client = load_artist_models()
    print("Все агенты и клиенты готовы.")
    return ingestor, scripter, artist_client

ingestor_agent, scripter_agent, artist_client = load_all_models()

with st.sidebar:
    st.header("⚙️ Настройки комикса")
    style_choice = st.selectbox("1. Выберите стиль комикса:", ("Американский комикс 80-х", "Современная манга", "Нуарный детектив", "Детская иллюстрация"))
    audience_choice = st.selectbox("2. Выберите целевую аудиторию:", ("Для детей 10 лет", "Для подростков", "Для взрослых экспертов"))
    max_pages_choice = st.slider("3. Количество страниц:", min_value=1, max_value=5, value=1, help="Выберите, сколько тематических страниц комикса сгенерировать.")
    consistent_chars = st.checkbox("Единые персонажи для всего комикса", value=True, help="Если включено, AI придумает одних и тех же героев для всех страниц.")
    seed_choice = st.number_input("Seed генерации", min_value=-1, value=-1, help="Введите число для воспроизводимых результатов. -1 для случайного.")

STYLE_KEYWORDS = {
    "Американский комикс 80-х": "80s comic book art, character-focused, bold outlines, halftone shading",
    "Современная манга": "dynamic black and white manga art, clean sharp lines, screentone shading, character-focused",
    "Нуарный детектив": "cinematic noir comic art, high-contrast black and white, dramatic chiaroscuro lighting",
    "Детская иллюстрация": "charming children's book illustration, cute cartoon style, simple characters, pastel colors"
}

st.title("AI-конвертер документов в комиксы 📜➡️🖼️")
st.markdown("Загрузите документ, настройте параметры в боковой панели и нажмите 'Создать комикс!'")

uploaded_file = st.file_uploader("Загрузите ваш PDF документ", type="pdf")
temp_pdf_path = "temp_uploaded_file.pdf"

if uploaded_file is not None:
    with open(temp_pdf_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    if st.button("✨ Создать комикс!", key="generate_button", type="primary"):
        st.session_state.generation_complete = False
        st.session_state.editor_data = []
        st.session_state.final_pages = []

        with st.status("🚀 Запускаю конвейер...", expanded=True) as status:
            status.update(label="Шаг 1: Читаю и распознаю документ...")
            document_text = ingestor_agent.process_pdf(temp_pdf_path)
            st.write("✅ Документ успешно прочитан!")
            
            status.update(label="Шаг 2: Создаю план и пишу сценарии...")
            scenarios = scripter_agent.generate_themed_scripts(document_text, style_choice, audience_choice, max_pages=max_pages_choice, use_consistent_characters=consistent_chars)
            
            if not scenarios:
                st.error("Не удалось сгенерировать ни одного сценария. Попробуйте изменить документ или настройки.")
            else:
                st.write(f"✅ Сценарии для {len(scenarios)} страниц комикса готовы!")
                
                editor_data_buffer = []
                for i, scenario in enumerate(scenarios):
                    page_num = i + 1
                    status.update(label=f"Шаг 3.{page_num}: Рисую 4 панели для страницы '{scenario.get('title', '')}'...")
                    
                    if scenario and scenario.get("scenes"):
                        style_keywords = STYLE_KEYWORDS.get(style_choice, "comic book style")
                        images = generate_all_panels_in_parallel(client=artist_client, scenario=scenario, style_keywords=style_keywords, seed=seed_choice)
                        
                        editor_data_buffer.append({'scenario': scenario, 'images': images})
                        st.write(f"✅ Все панели для страницы {page_num} нарисованы!")
                
                st.session_state.editor_data = editor_data_buffer
                st.session_state.generation_complete = True
        
        st.success("🎉 Первичная генерация завершена! Теперь вы можете отредактировать результат ниже.")

if st.session_state.get('generation_complete', False):
    st.markdown("---")
    st.header("✍️ Редактор комикса")
    st.info("Здесь вы можете изменить текст подписей и перерисовать отдельные панели перед финальной сборкой.")

    for i, page_data in enumerate(st.session_state.editor_data):
        st.subheader(f"Страница {i+1}: {page_data['scenario']['title']}")
        cols = st.columns(4)
        
        for j, scene in enumerate(page_data['scenario']['scenes']):
            with cols[j]:
                st.image(page_data['images'][j], use_column_width=True)
                
                new_caption = st.text_area(
                    f"Текст панели {j+1}",
                    value=scene.get('caption', scene.get('dialogue', '')),
                    key=f"caption_{i}_{j}"
                )
                st.session_state.editor_data[i]['scenario']['scenes'][j]['caption'] = new_caption
                
                if st.button("🔄 Перерисовать", key=f"redraw_{i}_{j}"):
                    with st.spinner("Перерисовываю..."):
                        style_keywords = STYLE_KEYWORDS.get(style_choice, "comic book style")
                        new_image = generate_panel_image(
                            client=artist_client,
                            scene=st.session_state.editor_data[i]['scenario']['scenes'][j],
                            style_keywords=style_keywords,
                            seed=seed_choice
                        )
                        st.session_state.editor_data[i]['images'][j] = new_image
                        st.rerun()

    st.markdown("---")
    
    if st.button("✅ Собрать и показать итоговый комикс", type="primary"):
        final_pages_buffer = []
        with st.spinner("Собираю финальные страницы..."):
            for i, page_data in enumerate(st.session_state.editor_data):
                final_page_image = create_comic_page(
                    scenario=page_data['scenario'],
                    images=page_data['images'],
                    style=style_choice
                )
                page_filename = f"comic_page_{i+1}_{style_choice.replace(' ', '_')}.png"
                final_pages_buffer.append((final_page_image, page_filename))
        st.session_state.final_pages = final_pages_buffer
        st.success("Комикс собран!")


def convert_images_to_pdf_in_memory(page_images: list):
    if not page_images:
        return None
    
    pdf_buffer = BytesIO()
    
    page_images[0].save(
        pdf_buffer,
        format="PDF",
        save_all=True,
        append_images=page_images[1:],
        resolution=100.0
    )

    return pdf_buffer.getvalue()


if st.session_state.final_pages:
    st.header("✅ Готовый комикс")
    
    st.info("Вы можете скачать весь комикс как единый PDF-файл или каждую страницу отдельно в формате PNG.")
    list_of_pil_images = [page[0] for page in st.session_state.final_pages]
    pdf_bytes = convert_images_to_pdf_in_memory(list_of_pil_images)
    st.download_button(
        label="📥 Скачать весь комикс (PDF)",
        data=pdf_bytes,
        file_name="ai_generated_comic.pdf",
        mime="application/pdf",
        type="primary"
    )
    st.markdown("---")

    num_columns = 3
    
    for i in range(0, len(st.session_state.final_pages), num_columns):
        cols = st.columns(num_columns)
        
        current_pages_chunk = st.session_state.final_pages[i : i + num_columns]
        
        for col, page_data in zip(cols, current_pages_chunk):
            page_image, page_filename = page_data
            
            with col:
                st.image(page_image, caption=f"Страница {st.session_state.final_pages.index(page_data) + 1}", use_column_width=True)
                
                buf = BytesIO()
                page_image.save(buf, format="PNG")
                png_bytes = buf.getvalue()

                st.download_button(
                    label=f"Скачать (PNG)",
                    data=png_bytes,
                    file_name=page_filename,
                    mime="image/png",
                    key=f"download_button_{st.session_state.final_pages.index(page_data)}" 
                )
    st.markdown("---")


if os.path.exists(temp_pdf_path):
    os.remove(temp_pdf_path)