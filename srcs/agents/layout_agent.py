from PIL import Image, ImageDraw, ImageFont
import os

def format_dialogue(dialogue_data) -> str:
    """
    Функция для форматирования диалогов любого формата.
    """
    if not dialogue_data:
        return ""
    
    if isinstance(dialogue_data, str):
        return dialogue_data.replace("<br>", "\n").strip()
    
    if isinstance(dialogue_data, dict):
        values = [str(v) for v in dialogue_data.values() if str(v).strip()]
        return ": ".join(values).strip()
        
    if isinstance(dialogue_data, list):
        return "\n".join(format_dialogue(item) for item in dialogue_data).strip()

    return ""


def create_comic_page(scenario: dict, images: list[Image.Image], style: str) -> Image.Image:
    if not images: return Image.new('RGB', (850, 1100), 'white')
    page_width, page_height = 850, 1100
    padding = 25
    canvas = Image.new('RGB', (page_width, page_height), 'white')
    draw = ImageDraw.Draw(canvas)
    try:
        font_path = os.path.join(os.path.dirname(__file__), '..', 'fonts', 'DejaVuSans.ttf')
        title_font = ImageFont.truetype(font_path, 30)
    except IOError:
        title_font = ImageFont.load_default()
    from textwrap import TextWrapper
    title_text = scenario.get("title", "My Comic")
    char_width_approx = title_font.size * 0.6
    wrapper = TextWrapper(width=int((page_width - 2 * padding) / char_width_approx) if char_width_approx > 0 else 50)
    wrapped_title = wrapper.fill(text=title_text)
    draw.multiline_text((padding, padding), wrapped_title, font=title_font, fill="black")
    title_bbox = draw.multiline_textbbox((padding, padding), wrapped_title, font=title_font)
    panels_start_y = title_bbox[3] + padding
    panel_width = (page_width - 3 * padding) // 2
    remaining_height_for_panels = page_height - panels_start_y - 3 * padding
    panel_height = remaining_height_for_panels // 2
    if panel_height <= 0: panel_height = 100
    positions = [
        (padding, panels_start_y), (padding * 2 + panel_width, panels_start_y),
        (padding, panels_start_y + panel_height + padding), (padding * 2 + panel_width, panels_start_y + panel_height + padding)
    ]

    for i, img in enumerate(images):
        if i >= len(positions) or not isinstance(img, Image.Image): continue
        
        img = img.resize((panel_width, panel_height))
        canvas.paste(img, positions[i])
        
        x1, y1 = positions[i]; x2, y2 = x1 + panel_width, y1 + panel_height
        draw.rectangle([x1, y1, x2, y2], outline="black", width=4)
        
        dialogue_raw = scenario["scenes"][i].get("dialogue") or scenario["scenes"][i].get("caption", "")
        
        dialogue = format_dialogue(dialogue_raw)
        
        if dialogue:
            text_box_padding = 10
            box_x1, box_y1 = x1 + 8, y2 - 100
            box_x2, box_y2 = x2 - 8, y2 - 8
            text_area_width = box_x2 - box_x1 - 2 * text_box_padding
            text_area_height = box_y2 - box_y1 - 2 * text_box_padding
            font_size = 22; font = None; wrapped_text = dialogue
            while font_size > 9:
                font = ImageFont.truetype(font_path, font_size)
                temp_wrapped_lines = []
                words = dialogue.split() 
                current_line = ""
                for word in words:
                    if draw.textlength(current_line + word + ' ', font=font) <= text_area_width:
                        current_line += word + ' '
                    else:
                        temp_wrapped_lines.append(current_line.strip())
                        current_line = word + ' '
                temp_wrapped_lines.append(current_line.strip())
                wrapped_text = "\n".join(temp_wrapped_lines)
                text_bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
                text_height = text_bbox[3] - text_bbox[1]
                if text_height <= text_area_height: break
                font_size -= 1
            draw.rectangle([box_x1, box_y1, box_x2, box_y2], fill="white", outline="black", width=2)
            draw.multiline_text((box_x1 + text_box_padding, box_y1 + text_box_padding), wrapped_text, font=font, fill="black")
            
    return canvas