import fitz
import easyocr
import numpy as np
from PIL import Image
import io

class IngestorAgent:
    def __init__(self, languages=['ru', 'en']):
        print("Загрузка OCR модели... Может занять некоторое время при первом запуске.")
        self.ocr_reader = easyocr.Reader(languages)
        print("OCR модель успешно загружена.")

    def _is_scanned_page(self, page, text_threshold=100):

        text = page.get_text("text")
        return len(text.strip()) < text_threshold

    def _ocr_page(self, page):
        pix = page.get_pixmap(dpi=800)
        img_bytes = pix.tobytes("png")
        image = Image.open(io.BytesIO(img_bytes))
        
        image_np = np.array(image)
        
        result = self.ocr_reader.readtext(image_np, detail=0, paragraph=True)
        
        return "\n".join(result)

    def process_pdf(self, pdf_path: str) -> str:
        print(f"Обработка документа: {pdf_path}")
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"Ошибка при открытии PDF: {e}")
            return ""

        full_text = []
        
        for i, page in enumerate(doc):
            print(f"Обработка страницы {i + 1}/{len(doc)}...")
            if self._is_scanned_page(page):
                print(f"  Страница {i + 1} определена как скан. Запуск OCR...")
                text = self._ocr_page(page)
                full_text.append(text)
            else:
                print(f"  Страница {i + 1} содержит текст. Прямое извлечение.")
                text = page.get_text("text")
                full_text.append(text)
        
        doc.close()
        print("Обработка документа завершена.")
        return "\n\n--- Page Break ---\n\n".join(full_text)

if __name__ == '__main__':
    ingestor = IngestorAgent()
    
    try:
        document_text = ingestor.process_pdf("/content/Правила внутреннего распорядка для пациентов.pdf")
        print("\n--- РЕЗУЛЬТАТ ---")
        print(document_text)
    except FileNotFoundError:
        print("\nОшибка: Тестовый PDF не найден. Укажите правильный путь.")