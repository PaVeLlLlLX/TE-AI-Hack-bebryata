# Логика агента 1 (Сценарист)
# agents/scripter_agent.py

import os
import json
import torch
from transformers import pipeline, T5ForConditionalGeneration, T5Tokenizer
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

# --- КОНФИГУРАЦИЯ ---
# Убедитесь, что ваш OpenAI API ключ находится в переменных окружения
# Например, в файле .env, который загружается в app.py
# openai.api_key = os.getenv("OPENAI_API_KEY")

class ScripterAgent:
    def __init__(self):
        """
        Инициализирует агента, загружая модели для суммаризации и настраивая LLM-клиент.
        """
        print("Загрузка агента-сценариста...")
        
        # 1. Загрузка модели для суммаризации
        model_name = "cointegrated/rut5-base-absum"
        print(f"Загрузка модели суммаризации: {model_name}. Может занять некоторое время...")
        
        # Определяем устройство (GPU если доступно)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Используемое устройство для суммаризации: {device}")
        
        self.tokenizer = T5Tokenizer.from_pretrained(model_name)
        self.model = T5ForConditionalGeneration.from_pretrained(model_name).to(device)
        # Использование pipeline не всегда удобно для кастомной логики чанкинга,
        # поэтому будем использовать модель и токенизатор напрямую.
        
        print("Модель суммаризации загружена.")

        # 2. Загрузка шаблона промпта для LLM
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self, filename="scripter_prompt.txt"):
        """Загружает шаблон промпта из файла, используя абсолютный путь."""
        # Получаем директорию, в которой находится текущий файл (srcs/agents)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Поднимаемся на один уровень вверх (в srcs) и заходим в prompts
        filepath = os.path.join(current_dir, '..', 'prompts', filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            print(f"ОШИБКА: Файл с промптом не найден по пути {filepath}")
            # Возвращаем "заглушку", чтобы избежать падения
            return "Create a comic script from this text: {summary_text}"
        
    def _clean_text(self, text: str) -> str:
        """Очищает текст от артефактов OCR и бессмысленных строк."""
        print("Очистка распознанного текста...")
        # Удаляем строки, содержащие в основном не-буквенные символы или короткие слова
        # Например, "х14 хб х12 6 8 В А"
        cleaned_lines = []
        for line in text.split('\n'):
            # Удаляем строки с разрывами страниц
            if '--- Page Break ---' in line:
                continue
            # Считаем количество букв в строке
            alpha_chars = sum(c.isalpha() for c in line)
            # Считаем общее количество символов (не пробелы)
            total_chars = sum(1 for c in line if not c.isspace())
            
            # Если букв меньше 50% от всех символов, скорее всего это мусор
            if total_chars > 0 and (alpha_chars / total_chars < 0.5):
                print(f"  Пропускаю мусорную строку: {line}")
                continue
            
            cleaned_lines.append(line)
            
        return "\n".join(cleaned_lines)

    def _summarize_text(self, text: str, max_chunk_length=1500, summary_max_length=250) -> str:
        """
        Суммаризирует длинный текст, разбивая его на части.
        Модели T5 имеют ограничение на длину входа, поэтому это необходимо.
        """
        print("Начинаю суммирование текста...")
        # Разбиваем текст на параграфы
        paragraphs = text.split('\n')
        
        chunks = []
        current_chunk = ""
        for p in paragraphs:
            if len(current_chunk) + len(p) + 1 < max_chunk_length:
                current_chunk += p + "\n"
            else:
                chunks.append(current_chunk)
                current_chunk = p + "\n"
        chunks.append(current_chunk) # Добавляем последний чанк

        summaries = []
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            
            print(f"  Суммирую часть {i+1}/{len(chunks)}...")
            try:
                input_ids = self.tokenizer.encode(chunk, return_tensors="pt").to(self.model.device)
                
                # Генерация саммари
                generated_ids = self.model.generate(
                    input_ids,
                    max_length=summary_max_length,
                    min_length=30,
                    num_beams=4,
                    length_penalty=2.0,
                    early_stopping=True
                )
                
                summary = self.tokenizer.decode(generated_ids[0], skip_special_tokens=True)
                summaries.append(summary)
            except Exception as e:
                print(f"    Ошибка при суммировании части {i+1}: {e}")

        final_summary = "\n".join(summaries)
        print("Суммирование завершено.")
        return final_summary

    def _create_scenario_from_summary(self, summary_text: str, style: str, audience: str) -> dict:
        print("Генерация сценария на основе сводки (используя GigaChat)...")
        
        credentials = os.getenv("GIGACHAT_CREDENTIALS")
        if not credentials:
            print("ОШИБКА: GIGACHAT_CREDENTIALS не найдены в .env")
            return {"title": "Ошибка конфигурации", "scenes": []}

        filled_prompt = self.prompt_template.format(
            summary_text=summary_text, style=style, audience=audience
        )

        try:
            with GigaChat(credentials=credentials, verify_ssl_certs=False) as giga:
                chat = Chat(
                    messages=[Messages(role=MessagesRole.USER, content=filled_prompt)],
                    temperature=0.7,
                    max_tokens=1500,
                )
                response = giga.chat(chat)
                scenario_json_str = response.choices[0].message.content
                
                # Очистка, аналогичная YandexGPT
                start_index = scenario_json_str.find('{')
                end_index = scenario_json_str.rfind('}') + 1
                
                if start_index == -1 or end_index == 0:
                    raise ValueError(f"JSON объект не найден в ответе модели: {scenario_json_str}")
                    
                clean_json_str = scenario_json_str[start_index:end_index]
                return json.loads(clean_json_str)

        except Exception as e:
            print(f"ОШИБКА при вызове GigaChat API: {e}")
            return {"title": "Ошибка генерации", "scenes": []}

    def generate_script(self, document_text: str, style: str, audience: str) -> dict:
        """
        Полный пайплайн: принимает сырой текст, суммирует его и генерирует сценарий.
        """
        if not document_text.strip():
            return {"title": "Пустой документ", "scenes": []}
        
        # ШАГ 0: Очистка текста
        cleaned_text = self._clean_text(document_text)
            
        if len(cleaned_text) < 500:
            print("Текст слишком короткий, пропускаю суммирование.")
            summary = cleaned_text
        else:
            # Шаг 1: Суммаризация
            summary = self._summarize_text(cleaned_text)
        
        if not summary.strip():
             print("Суммаризация не дала результата. Попытка генерации из полного текста.")
             summary = document_text[:4000] # Обрезаем, чтобы не превысить лимиты

        # Для отладки в Streamlit можно будет вывести саммари
        print("\n--- Итоговая сводка ---")
        print(summary)
        print("---------------------\n")
        
        # Шаг 2: Генерация сценария
        script = self._create_scenario_from_summary(summary, style, audience)
        
        # Добавляем сводку в результат для возможного отображения в UI
        script['summary'] = summary
        
        return script

# --- Блок для самостоятельного тестирования агента ---
if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    
    if not os.getenv("GIGACHAT_CREDENTIALS"):
        print("Ключ GIGACHAT_CREDENTIALS не найден. Установите его в .env файле для запуска теста.")
    else:
        # Пример текста (взято из инструкции по пожарной безопасности)
        test_text = """
        При возникновении пожара или его признаков (дыма, запаха гари) необходимо немедленно сообщить об этом по телефону 101 или 112, указав точный адрес.
        Примите меры по эвакуации людей. Отключите электроэнергию и газоснабжение.
        Используйте первичные средства пожаротушения (огнетушители, вода, песок) для тушения огня.
        Не открывайте окна и двери, чтобы не создавать приток воздуха к очагу горения.
        Если помещение сильно задымлено, передвигайтесь пригнувшись к полу, прикрыв органы дыхания влажной тканью.
        Не пользуйтесь лифтом во время пожара.
        """

        # Инициализация агента
        scripter = ScripterAgent()
        
        # Генерация сценария
        comic_script = scripter.generate_script(
            document_text=test_text,
            style="Американский комикс 80-х",
            audience="Для детей 10 лет"
        )
        
        # Вывод результата
        print("\n--- РЕЗУЛЬТАТ ГЕНЕРАЦИИ СЦЕНАРИЯ ---")
        print(json.dumps(comic_script, indent=2, ensure_ascii=False))