# agents/scripter_agent.py

import os
import json
import time
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole


def is_predominantly_cyrillic(text: str, threshold: float = 0.7) -> bool:
    """Проверяет, состоит ли строка преимущественно из кириллических символов."""
    if not text or not text.strip(): return False
    cyrillic_chars = sum(1 for char in text if 'а' <= char.lower() <= 'я')
    total_letters = sum(1 for char in text if char.isalpha())
    if total_letters == 0: return False
    return (cyrillic_chars / total_letters) >= threshold

def is_predominantly_latin(text: str, threshold: float = 0.7) -> bool:
    """Проверяет, состоит ли строка преимущественно из латинских символов (английский)."""
    if not text or not text.strip(): return False
    latin_chars = sum(1 for char in text if 'a' <= char.lower() <= 'z')
    total_letters = sum(1 for char in text if char.isalpha())
    if total_letters == 0: return False
    return (latin_chars / total_letters) >= threshold

class ScripterAgent:
    def __init__(self):
        print("Загрузка агента-сценариста...")
        self.script_prompt_template = self._load_prompt_template("scripter_prompt.txt")
        self.theme_prompt_template = self._load_prompt_template("theme_extractor_prompt.txt")

    def _load_prompt_template(self, filename: str):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(current_dir, '..', 'prompts', filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            print(f"ОШИБКА: Файл с промптом не найден по пути {filepath}")
            return None
        
    def _clean_and_filter_text(self, text: str) -> str:
        """
        Очищает ВЕСЬ текст, сохраняя только русские и английские строки
        и удаляя OCR-артефакты.
        """
        print("Очистка и фильтрация всего документа (сохраняем RU/EN)...")
        text_no_breaks = text.replace("--- Page Break ---", "\n")
        
        cleaned_lines = []
        for line in text_no_breaks.split('\n'):
            if not (is_predominantly_cyrillic(line) or is_predominantly_latin(line)):
                if line.strip(): print(f"    Фильтрую строку на другом языке: {line[:70]}...")
                continue

            alpha_chars = sum(c.isalpha() for c in line)
            total_chars = sum(1 for c in line if not c.isspace())
            if total_chars > 5 and (alpha_chars / total_chars < 0.6):
                print(f"    Фильтрую OCR-мусор: {line}")
                continue
                
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    def _extract_themes(self, document_text: str) -> list[dict]:
        """Этап 1: Вызывает GigaChat в роли 'Аналитика' для выделения тем."""
        print("  Этап 1: Выделение ключевых тем из документа...")
        if not self.theme_prompt_template:
            print("  ОШИБКА: Промпт для выделения тем не загружен.")
            return []
            
        credentials = os.getenv("GIGACHAT_CREDENTIALS")
        if not credentials:
            print("  ОШИБКА: GIGACHAT_CREDENTIALS не найдены.")
            return []

        filled_prompt = self.theme_prompt_template.format(document_text=document_text)
        try:
            with GigaChat(credentials=credentials, verify_ssl_certs=False) as giga:
                chat = Chat(messages=[Messages(role=MessagesRole.USER, content=filled_prompt)], temperature=0.5, max_tokens=2000)
                response = giga.chat(chat)
                themes_json_str = response.choices[0].message.content
                start_index = themes_json_str.find('[')
                end_index = themes_json_str.rfind(']') + 1
                if start_index == -1 or end_index == 0:
                    raise ValueError("JSON-массив не найден в ответе модели")
                themes = json.loads(themes_json_str[start_index:end_index])
                print(f"  Успешно выделено {len(themes)} тем.")
                return themes
        except Exception as e:
            print(f"  ОШИБКА при выделении тем: {e}")
            return []

    def _create_scenario_from_summary(self, summary_text: str, style: str, audience: str, max_retries: int = 3) -> dict:
        """
        Этап 2: Вызывает GigaChat в роли 'Сценариста' с механизмом повторных попыток.
        """
        print("    Этап 2: Генерация сценария для темы...")
        if not self.script_prompt_template:
            print("    ОШИБКА: Промпт для генерации сценария не загружен.")
            return {}
            
        credentials = os.getenv("GIGACHAT_CREDENTIALS")
        if not credentials: return {}

        filled_prompt = self.script_prompt_template.format(summary_text=summary_text, style=style, audience=audience)
        
        for attempt in range(max_retries):
            print(f"      Попытка {attempt + 1}/{max_retries}...")
            try:
                with GigaChat(credentials=credentials, verify_ssl_certs=False) as giga:
                    chat = Chat(messages=[Messages(role=MessagesRole.USER, content=filled_prompt)], temperature=0.7 + (attempt * 0.1), max_tokens=1500)
                    response = giga.chat(chat)
                    scenario_json_str = response.choices[0].message.content
                    
                    start_index = scenario_json_str.find('{')
                    end_index = scenario_json_str.rfind('}') + 1
                    
                    if start_index == -1 or end_index == 0:
                        raise ValueError("JSON-объект не найден в ответе модели")
                    
                    clean_json_str = scenario_json_str[start_index:end_index]
                    
                    parsed_json = json.loads(clean_json_str)
                    
                    print("      Успешная генерация и парсинг JSON!")
                    return parsed_json

            except (json.JSONDecodeError, ValueError) as e:
                print(f"      ОШИБКА парсинга JSON на попытке {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    print("      Пробую сгенерировать заново...")
                    time.sleep(1) 
                else:
                    print("      Достигнут лимит попыток. Не удалось сгенерировать валидный сценарий для этой темы.")
                    return {} 
        
        return {}

    def generate_themed_scripts(self, document_text: str, style: str, audience: str) -> list[dict]:
        """
        Главный метод: очищает текст, выделяет темы, затем генерирует сценарий для каждой темы.
        """
        if not document_text.strip(): return []
        
        cleaned_document = self._clean_and_filter_text(document_text)
        if len(cleaned_document) < 200:
            print("После очистки в документе осталось слишком мало текста. Прерываю.")
            return []
            
        themes = self._extract_themes(cleaned_document)
        if not themes:
            print("Не удалось выделить темы из документа.")
            return []
            
        all_scenarios = []
        for i, theme in enumerate(themes):
            print(f"\n--- Обработка темы {i+1}/{len(themes)}: '{theme.get('theme_title', 'Без названия')}' ---")
            
            theme_summary = theme.get("theme_summary")
            if not theme_summary:
                print("  В теме отсутствует содержание (summary), пропускаю.")
                continue

            script = self._create_scenario_from_summary(theme_summary, style, audience)
            
            if script and script.get("scenes"):
                script['title'] = theme.get("theme_title", script.get("title", f"Комикс по теме {i+1}"))
                script['summary'] = theme_summary
                all_scenarios.append(script)
            else:
                print(f"  Не удалось сгенерировать сценарий для темы.")
                
        return all_scenarios