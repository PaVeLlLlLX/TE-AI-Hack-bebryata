# agents/artist_agent.py
import os
import requests
import time
import json
from PIL import Image
from io import BytesIO
import streamlit as st
import base64

class KandinskyAPI:
    def __init__(self, api_key, secret_key):
        self.API_KEY = api_key
        self.SECRET_KEY = secret_key
        self.URL = 'https://api-key.fusionbrain.ai/key/api/v1' 
        self.AUTH_HEADERS = {
            'X-Key': f'Key {self.API_KEY}',
            'X-Secret': f'Secret {self.SECRET_KEY}',
        }

    def _handle_response(self, response: requests.Response):
        """Проверяет ответ сервера и выбрасывает исключение в случае ошибки."""
        if response.status_code in [200, 201]:
            return response.json()
        else:
            error_message = f"Ошибка API: Статус {response.status_code}. Ответ: {response.text}"
            print(error_message)
            raise RuntimeError(error_message)

    def get_model(self):
        response = requests.get(f'{self.URL}/pipelines', headers=self.AUTH_HEADERS)
        data = self._handle_response(response)
        for model in data:
            if model.get('name') == 'Kandinsky Split 3.0':
                return model['id']
        raise RuntimeError("Не удалось найти модель Kandinsky Split 3.0 в списке доступных.")

    def generate(self, prompt, pipeline_id, width=1024, height=1024):
        params = {"type": "GENERATE", "numImages": 1, "width": width, "height": height, "generateParams": {"query": prompt}}
        data = {'pipeline_id': (None, pipeline_id), 'params': (None, json.dumps(params), 'application/json')}
        response = requests.post(f'{self.URL}/pipeline/run', headers=self.AUTH_HEADERS, files=data)
        data = self._handle_response(response)
        return data['uuid']

    def check_generation(self, request_id, attempts=20, delay=10):
        while attempts > 0:
            response = requests.get(f'{self.URL}/pipeline/status/{request_id}', headers=self.AUTH_HEADERS)
            data = self._handle_response(response)
            if data['status'] == 'DONE':
                image_base64 = data['result']['files'][0]
                image_bytes = base64.b64decode(image_base64)
                return image_bytes
            
            if data['status'] == 'FAIL':
                raise RuntimeError(f"Генерация не удалась. Ошибка: {data.get('errorDescription', 'Неизвестная ошибка')}")

            print(f"  Статус: {data['status']}. Ожидание {delay} сек...")
            attempts -= 1
            time.sleep(delay)
        raise TimeoutError("Изображение не было сгенерировано за отведенное время.")

@st.cache_resource
def load_artist_models():
    print("Инициализация клиента Kandinsky API...")
    api_key = os.getenv("FUSION_API_KEY")
    secret_key = os.getenv("FUSION_SECRET_KEY")
    if not api_key or not secret_key:
        st.error("Ключи FUSION_API_KEY или FUSION_SECRET_KEY не найдены в .env файле!")
        return None
    client = KandinskyAPI(api_key, secret_key)
    print("Клиент Kandinsky API готов.")
    return client


def build_and_truncate_prompt(action_prompt, location_desc, character_descs, style_keywords, max_len=950):
    """
    Интеллигентно собирает и обрезает промпт, чтобы он не превышал лимит API.
    """
    parts_in_order = [
        action_prompt,
        f"Characters involved: {', '.join(character_descs)}." if character_descs else "",
        f"Location: {location_desc}",
        f"Style: {style_keywords}"
    ]
    
    final_prompt = ""
    for part in parts_in_order:
        if not part.strip() or part.strip() == ".": continue
        
        if len(final_prompt) + len(part) + 2 > max_len:
            print(f"--- ВНИМАНИЕ: Промпт был программно обрезан, чтобы не превысить лимит {max_len} символов. ---")
            print(f"--- Отброшена часть: '{part[:100]}...'")
            break
            
        final_prompt += f"{part}. "
        
    return final_prompt.strip()


def generate_panel_image(client: KandinskyAPI, scenario: dict, scene_index: int, style_keywords: str) -> Image.Image:
    """
    Собирает полный, контекстно-богатый промпт и генерирует изображение.
    """
    if not client:
        return Image.new('RGB', (1024, 1024), 'grey')

    scene = scenario['scenes'][scene_index]
    bible = scenario.get('story_bible', {})
    
    action_prompt = scene.get('image_prompt', '')
    location_desc = bible.get('main_location', '')
    
    character_descs = []
    for char in bible.get('main_characters', []):
        character_descs.append(f"{char.get('name', '')} ({char.get('description', '')})")
    
    full_prompt = build_and_truncate_prompt(action_prompt, location_desc, character_descs, style_keywords)
    
    print(f"Генерирую изображение Kandinsky с ФИНАЛЬНЫМ промптом: {full_prompt}")
    
    try:
        pipeline_id = client.get_model()
        uuid = client.generate(full_prompt, pipeline_id)
        image_bytes = client.check_generation(uuid)
        return Image.open(BytesIO(image_bytes))
    except Exception as e:
        print(f"ОШИБКА при вызове Kandinsky API: {e}")
        st.error(f"Произошла ошибка при генерации изображения: {e}")
        return Image.new('RGB', (1024, 1024), 'red')