import os
import json
import time
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from json_repair import loads as repair_json_loads


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
        self.planner_prompt_template = self._load_prompt_template("planner_prompt.txt")
        self.scripter_prompt_template = self._load_prompt_template("scripter_prompt.txt")
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
            if len(line.strip()) < 5:
                    continue
            
            if not (is_predominantly_cyrillic(line)):
                if line.strip(): print(f"    Фильтрую строку на другом языке: {line[:70]}...")
                continue
            alpha_chars = sum(c.isalpha() for c in line); total_chars = sum(1 for c in line if not c.isspace())
            if total_chars > 5 and (alpha_chars / total_chars < 0.6): print(f"    Фильтрую OCR-мусор: {line}"); continue
            cleaned_lines.append(line)
        print("\n".join(cleaned_lines))
        return "\n".join(cleaned_lines)
    

    def _call_llm(self, prompt: str, temperature: float = 0.5, max_tokens=4000, max_retries: int = 3) -> str:
        credentials = os.getenv("GIGACHAT_CREDENTIALS")
        if not credentials:
            raise ValueError("GIGACHAT_CREDENTIALS не найдены.")
        
        for attempt in range(max_retries):
            print(f"  [LLM Call]: Попытка {attempt + 1}/{max_retries}...")
            try:
                with GigaChat(credentials=credentials, verify_ssl_certs=False, timeout=120) as giga:
                    chat = Chat(
                        messages=[Messages(role=MessagesRole.USER, content=prompt)],
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    response = giga.chat(chat)
                    response_content = response.choices[0].message.content
                    
                    if not response_content or response_content.strip() in ["[]", "{}"]:
                        print(f"  [ПРЕДУПРЕЖДЕНИЕ]: GigaChat вернул пустой ответ на попытке {attempt + 1}.")
                        raise ValueError("Получен пустой ответ от API")

                    print("  [LLM Call]: Ответ от GigaChat успешно получен.")
                    return response_content

            except Exception as e:
                print(f"  [ОШИБКА] на попытке {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    print(f"  [LLM Call]: Жду {wait_time} секунд перед следующей попыткой...")
                    time.sleep(wait_time)
                else:
                    print(f"  [ОШИБКА]: Достигнут лимит попыток. Не удалось получить ответ от GigaChat.")
                    return ""
        return ""
    
        
    def _extract_json_from_response(self, response_str: str) -> dict | list:
        json_str = ""
        
        json_block_start = response_str.find("```json")
        if json_block_start != -1:
            start = json_block_start + len("```json")
            end = response_str.find("```", start)
            if end != -1:
                json_str = response_str[start:end].strip()
        
        if not json_str:
            first_char = next((char for char in response_str if char in ['{', '[']), None)
            if first_char == '{':
                start_bracket, end_bracket = '{', '}'
            elif first_char == '[':
                start_bracket, end_bracket = '[', ']'
            else:
                raise ValueError("В ответе не найдены символы начала JSON ('{' или '[').")

            start_index = response_str.find(start_bracket)
            end_index = response_str.rfind(end_bracket)
            if start_index != -1 and end_index != -1 and end_index > start_index:
                json_str = response_str[start_index : end_index + 1].strip()

        if not json_str:
            raise ValueError("Не удалось извлечь потенциальную JSON-строку из ответа.")

        try:
            print("  [Парсер]: Попытка распарсить стандартным методом...")
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"  [Парсер]: Стандартный метод не удался. Ошибка: {e}")
            print("  [Парсер]: Использование json_repair...")
            try:
                return repair_json_loads(json_str)
            except Exception as repair_e:
                print(f"  [Парсер]: json_repair не смог исправить JSON. Ошибка: {repair_e}")
                raise ValueError("Не удалось извлечь валидный JSON даже после попытки восстановления.")


    def _create_plan(self, document_text: str, num_pages: int) -> list[dict]:
        """
        Этап 1: Вызывает "Главного Редактора" для создания плана комикса.
        """
        print("\n--- Этап 1: Создание плана комикса (вызов 'Главного Редактора')... ---")
        if not self.planner_prompt_template:
            print("  ОШИБКА: Промпт для планировщика не загружен.")
            return []

        
        if not document_text.strip(): return []
        
        cleaned_document = self._clean_and_filter_text(document_text)
        if len(cleaned_document) < 150:
            print("Мало текста после очистки.")
            return []
        
        filled_prompt = self.planner_prompt_template.format(document_text=cleaned_document, num_pages=num_pages)

        try:
            response_str = self._call_llm(filled_prompt)
            print(f"--- ПОЛУЧЕН ПЛАН ОТ GIGACHAT ---\n{response_str}...\n--- КОНЕЦ ПЛАНА ---")
            plan = self._extract_json_from_response(response_str)
            print(f"  План успешно создан, {len(plan)} страниц запланировано.")
            return plan
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  ОШИБКА при создании плана: {e}")
            return []
    

    def _create_global_story_bible(self, document_text: str) -> list | None:
        print("\n--- Шаг 'Кастинг': Создание глобальных персонажей... ---")
        if not self.global_char_prompt_template:
            print("  ОШИБКА: Промпт для 'кастинга' не загружен.")
            return None
        
        filled_prompt = self.global_char_prompt_template.format(document_text=document_text)
        try:
            response_str = self._call_llm(filled_prompt)
            print(f"--- ПОЛУЧЕН СПИСОК ПЕРСОНАЖЕЙ ---\n{response_str}\n--- КОНЕЦ СПИСКА ---")
            bible = self._extract_json_from_response(response_str)
            characters = bible.get("main_characters")
            if characters:
                print(f"  Успешно создано {len(characters)} глобальных персонажей.")
                return characters
            return None
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  ОШИБКА при создании глобальных персонажей: {e}")
            return None

    def _create_script_from_plan_item(self, plan_item: dict, style: str, audience: str, global_characters: list = None) -> dict:
        page_title = plan_item.get("page_title", "Без названия")
        original_text = plan_item.get("original_text_chunk", "")
        print(f"\n--- Шаг 'Исполнитель': Генерация сценария для страницы '{page_title}'... ---")
        
        if global_characters:
            chars_json_string = json.dumps(global_characters, ensure_ascii=False, indent=2)
            character_instruction = f"Используй ТОЛЬКО следующих предопределенных персонажей. Включи их в 'story_bible' этого сценария."
        else:
            character_instruction = "Придумай 1-2 абстрактные роли для этой темы (например, 'Пользователь', 'Система'). Дай им краткое описание."
        
        filled_prompt = self.scripter_prompt_template.format(
            page_title=page_title,
            original_text_chunk=original_text,
            character_instruction=character_instruction,
            style=style,
            audience=audience
        )
        
        for attempt in range(2): # 2 попытки
            try:
                response_str = self._call_llm(filled_prompt)
                print(f"--- ПОЛУЧЕН СЦЕНАРИЙ ОТ GIGACHAT (Попытка {attempt+1}) ---\n{response_str}\n--- КОНЕЦ СЦЕНАРИЯ ---")
                parsed_json = self._extract_json_from_response(response_str)
                if parsed_json and parsed_json.get("scenes"):
                    print(f"  Сценарий для страницы '{page_title}' успешно создан.")
                    return parsed_json
            except (json.JSONDecodeError, ValueError) as e:
                print(f"  Ошибка парсинга JSON на попытке {attempt + 1}: {e}")
        
        print(f"  Не удалось сгенерировать сценарий для страницы '{page_title}'.")
        return {}

    def generate_themed_scripts(self, document_text: str, style: str, audience: str, max_pages: int, use_consistent_characters: bool) -> list[dict]:
        comic_plan = self._create_plan(document_text, max_pages)
        if not comic_plan:
            return []

        global_characters = None
        if use_consistent_characters:
            global_characters = self._create_global_story_bible(document_text)
            if not global_characters:
                print("  ПРЕДУПРЕЖДЕНИЕ: Не удалось создать глобальных персонажей, каждая страница будет использовать своих.")

        all_scenarios = []
        for plan_item in comic_plan:
            script = self._create_script_from_plan_item(
                plan_item=plan_item,
                style=style,
                audience=audience,
                global_characters=global_characters
            )
            if script:
                all_scenarios.append(script)
                
        return all_scenarios