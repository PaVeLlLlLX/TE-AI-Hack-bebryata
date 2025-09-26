import streamlit as st
from agents.ingestor_agent import IngestorAgent

st.title("AI-конвертер документов в комиксы")

@st.cache_resource
def load_agents():
    ingestor = IngestorAgent()
    # scripter = ScripterAgent()
    # ...
    return ingestor #, scripter, ...

ingestor_agent = load_agents()

uploaded_file = st.file_uploader("Загрузите ваш PDF документ", type="pdf")

if uploaded_file is not None:
    with open("Инструкция о мерах пожарной безопасности.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())

    if st.button("Создать комикс"):
        with st.spinner("Шаг 1/4: Читаю и распознаю документ..."):
            document_text = ingestor_agent.process_pdf("Инструкция о мерах пожарной безопасности.pdf")
            st.success("Документ успешно прочитан!")
            st.text_area("Распознанный текст", document_text, height=200)

        # with st.spinner("Шаг 2/4: Пишу сценарий..."):
        #     # Запускаем Агента 1
        #     script = scripter_agent.generate_script(document_text)
        #     st.success("Сценарий готов!")

        # ... и так далее по цепочке