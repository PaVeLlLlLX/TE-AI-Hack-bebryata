# agents/scripter_agent.py
import os
import json
import time
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

def is_predominantly_cyrillic(text: str, threshold: float = 0.7) -> bool:
    if not text or not text.strip(): return False
    cyrillic_chars = sum(1 for char in text if 'а' <= char.lower() <= 'я')
    total_letters = sum(1 for char in text if char.isalpha())
    if total_letters == 0: return False
    return (cyrillic_chars / total_letters) >= threshold

def is_predominantly_latin(text: str, threshold: float = 0.7) -> bool:
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
        self.global_char_prompt_template = self._load_prompt_template("global_character_prompt.txt")

    def _load_prompt_template(self, filename: str):
        current_dir = os.path.dirname(os.path.abspath(__file__)); filepath = os.path.join(current_dir, '..', 'prompts', filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f: return f.read()
        except FileNotFoundError:
            print(f"ОШИБКА: Файл с промптом не найден: {filepath}"); return None
        
    def _clean_and_filter_text(self, text: str) -> str:
        print("Очистка и фильтрация всего документа (сохраняем RU/EN)...")
        text_no_breaks = text.replace("--- Page Break ---", "\n"); cleaned_lines = []
        for line in text_no_breaks.split('\n'):
            if not (is_predominantly_cyrillic(line) or is_predominantly_latin(line)):
                if line.strip(): print(f"    Фильтрую строку на другом языке: {line[:70]}...")
                continue
            alpha_chars = sum(c.isalpha() for c in line); total_chars = sum(1 for c in line if not c.isspace())
            if total_chars > 5 and (alpha_chars / total_chars < 0.6): print(f"    Фильтрую OCR-мусор: {line}"); continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines)
    
    def _call_giga_chat(self, prompt: str, temperature: float = 0.7) -> str:
        """Универсальная функция для вызова GigaChat."""
        credentials = os.getenv("GIGACHAT_CREDENTIALS")
        if not credentials: raise ValueError("GIGACHAT_CREDENTIALS не найдены.")
        with GigaChat(credentials=credentials, verify_ssl_certs=False) as giga:
            chat = Chat(messages=[Messages(role=MessagesRole.USER, content=prompt)], temperature=temperature, max_tokens=2000)
            response = giga.chat(chat)
            return response.choices[0].message.content

    def _extract_themes(self, document_text: str, num_themes: int) -> list[dict]:
        """Этап 1: Вызывает GigaChat для выделения заданного числа тем."""
        print(f"  Этап 1: Выделение {num_themes} ключевых тем из документа...")
        if not self.theme_prompt_template:
            print("  ОШИБКА: Промпт для выделения тем не загружен.")
            return []

        filled_prompt = self.theme_prompt_template.format(document_text=document_text, num_themes=num_themes)
        
        try:
            response_str = self._call_giga_chat(filled_prompt, temperature=0.5)
            start = response_str.find('[')
            end = response_str.rfind(']') + 1
            if start == -1 or end == 0: raise ValueError("JSON-массив не найден")
            themes = json.loads(response_str[start:end])
            print(f"  Успешно выделено {len(themes)} тем.")
            return themes
        except Exception as e:
            print(f"  ОШИБКА при выделении тем: {e}")
            return []
    
    def _create_global_story_bible(self, document_text: str) -> list | None:
        """Шаг 0, "Кастинг". Создает глобальных персонажей."""
        print("  Шаг 0: Создание глобальных персонажей для всего комикса...")
        if not self.global_char_prompt_template: print("  ОШИБКА: Промпт для 'кастинга' не загружен."); return None
        
        filled_prompt = self.global_char_prompt_template.format(document_text=document_text)
        try:
            response_str = self._call_giga_chat(filled_prompt)
            start = response_str.find('{')
            end = response_str.rfind('}') + 1
            if start == -1 or end == 0: raise ValueError("JSON-объект не найден")
            bible = json.loads(response_str[start:end])
            characters = bible.get("main_characters")
            if characters: print(f"  Успешно создано {len(characters)} глобальных персонажей."); return characters
            return None
        except Exception as e:
            print(f"  ОШИБКА при создании глобальных персонажей: {e}")
            return None

    def _create_scenario_from_summary(self, summary_text: str, style: str, audience: str, global_characters: list = None, max_retries: int = 2) -> dict:
        """Этап 2: Вызывает GigaChat в роли 'Сценариста' с механизмом повторных попыток."""
        print("    Этап 2: Генерация сценария для темы...")
        if not self.script_prompt_template: print("    ОШИБКА: Промпт сценариста не загружен."); return {}

        if global_characters:
            chars_json_string = json.dumps(global_characters, ensure_ascii=False, indent=2)
            character_instruction = f"ИСПОЛЬЗУЙ СЛЕДУЮЩИХ ПРЕДОПРЕДЕЛЕННЫХ ПЕРСОНАЖЕЙ:\n{chars_json_string}\nВключи их в 'story_bible' этого сценария."
        else:
            character_instruction = "Придумай 1-2 главных персонажей для этой темы. Дай им подробное описание внешности, одежды и отличительных черт."
        
        filled_prompt = self.script_prompt_template.format(summary_text=summary_text, character_instruction=character_instruction, style=style, audience=audience)
        
        for attempt in range(max_retries):
            print(f"      Попытка {attempt + 1}/{max_retries}...");
            try:
                response_str = self._call_giga_chat(filled_prompt, temperature=0.7 + (attempt*0.1))
                start = response_str.find('{')
                end = response_str.rfind('}') + 1
                if start == -1 or end == 0: raise ValueError("JSON-объект не найден")
                parsed_json = json.loads(response_str[start:end])
                print("      Успешная генерация и парсинг JSON!")
                return parsed_json
            except (json.JSONDecodeError, ValueError) as e:
                print(f"      ОШИБКА парсинга JSON на попытке {attempt + 1}: {e}")
                if attempt < max_retries - 1: print("      Пробую сгенерировать заново..."); time.sleep(1)
                else: print("      Достигнут лимит попыток."); return {}
        return {}

    def generate_themed_scripts(self, document_text: str, style: str, audience: str, max_pages: int, use_consistent_characters: bool = False) -> list[dict]:
        """Главный метод, который теперь принимает max_pages от пользователя."""
        if not document_text.strip(): return []
        
        cleaned_document = self._clean_and_filter_text(document_text)
        if len(cleaned_document) < 200:
            print("Мало текста после очистки.")
            return []
        
        global_characters = None
        if use_consistent_characters:
            global_characters = self._create_global_story_bible(cleaned_document)
            if not global_characters:
                print("  ПРЕДУПРЕЖДЕНИЕ: Не удалось создать глобальных персонажей.")

        themes = self._extract_themes(cleaned_document, num_themes=max_pages)
        if not themes:
            print("Не удалось выделить темы.")
            return []
            
        all_scenarios = []
        for i, theme in enumerate(themes):
            print(f"\n--- Обработка темы {i+1}/{len(themes)}: '{theme.get('theme_title', 'Без названия')}' ---")
            theme_summary = theme.get("theme_summary")
            if not theme_summary:
                print("  Пропуск темы без содержания.")
                continue
            
            script = self._create_scenario_from_summary(theme_summary, style, audience, global_characters=global_characters)
            
            if script and script.get("scenes"):
                script['title'] = theme.get('theme_title', f"Комикс по теме {i+1}")
                script['summary'] = theme_summary
                all_scenarios.append(script)
            else:
                print(f"  Не удалось сгенерировать сценарий для темы.")
                
        return all_scenarios