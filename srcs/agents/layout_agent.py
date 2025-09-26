# agents/layout_agent.py
from PIL import Image, ImageDraw, ImageFont
import textwrap
import os

def create_comic_page(scenario: dict, images: list[Image.Image], style: str) -> Image.Image:
    """
    Собирает кадры и текст в одну страницу комикса с адаптивной версткой текста.
    """
    if not images:
        return Image.new('RGB', (850, 1100), 'white')

    page_width, page_height = 850, 1100
    padding = 25 # Сделаем отступы чуть больше для воздуха
    canvas = Image.new('RGB', (page_width, page_height), 'white')
    draw = ImageDraw.Draw(canvas)
    
    try:
        font_path = os.path.join(os.path.dirname(__file__), '..', 'fonts', 'DejaVuSans.ttf')
        # --- ИЗМЕНЕНИЕ: Уменьшаем размер шрифта заголовка ---
        title_font = ImageFont.truetype(font_path, 30) 
    except IOError:
        print(f"ОШИБКА: Шрифт не найден. Убедись, что 'DejaVuSans.ttf' лежит в папке 'srcs/fonts/'")
        title_font = ImageFont.load_default()

    # Рисуем заголовок
    draw.text((padding, padding), scenario.get("title", "My Comic"), font=title_font, fill="black")

    # Параметры сетки
    panel_width = (page_width - 3 * padding) // 2
    panel_height = (page_height - 4 * padding - 50) // 2 

    positions = [
        (padding, padding + 60),
        (padding * 2 + panel_width, padding + 60),
        (padding, padding * 2 + 60 + panel_height),
        (padding * 2 + panel_width, padding * 2 + 60 + panel_height)
    ]

    for i, img in enumerate(images):
        if i >= len(positions): break
        
        img = img.resize((panel_width, panel_height))
        canvas.paste(img, positions[i])
        
        x1, y1 = positions[i]
        x2, y2 = x1 + panel_width, y1 + panel_height
        draw.rectangle([x1, y1, x2, y2], outline="black", width=4)
        
        dialogue_raw = scenario["scenes"][i].get("dialogue") or scenario["scenes"][i].get("caption", "")
        dialogue = dialogue_raw.replace("<br>", "\n").strip()
        
        if dialogue:
            # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: АДАПТИВНЫЙ РАЗМЕР ШРИФТА ---
            
            # 1. Задаем параметры текстового блока
            text_box_padding = 10
            box_x1 = x1 + 5
            box_y1 = y2 - 90 # Увеличим высоту блока
            box_x2 = x2 - 5
            box_y2 = y2 - 5
            text_area_width = box_x2 - box_x1 - 2 * text_box_padding
            text_area_height = box_y2 - box_y1 - 2 * text_box_padding
            
            # 2. Подбираем оптимальный размер шрифта
            font_size = 20 # Начинаем с большого
            while font_size > 10: # Минимальный читаемый размер
                font = ImageFont.truetype(font_path, font_size)
                # Оборачиваем текст. Ширину подбираем примерно.
                wrapper = textwrap.TextWrapper(width=int(text_area_width / (font_size * 0.5)))
                wrapped_text = wrapper.fill(text=dialogue)
                
                # Проверяем, влезает ли текст в блок
                text_bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
                text_height = text_bbox[3] - text_bbox[1]
                
                if text_height <= text_area_height:
                    break # Размер подходит!
                
                font_size -= 1 # Уменьшаем размер и пробуем снова
            
            # 3. Рисуем блок и текст с подобранным шрифтом
            draw.rectangle([box_x1, box_y1, box_x2, box_y2], fill="white", outline="black", width=2)
            draw.multiline_text(
                (box_x1 + text_box_padding, box_y1 + text_box_padding),
                wrapped_text,
                font=font,
                fill="black"
            )

    return canvas