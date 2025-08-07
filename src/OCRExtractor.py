from pdf2image import convert_from_path
from PIL import Image
import pytesseract


pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

class OCRTextExtractor:
    def __init__(self, pdf_path: str, password: str = None):
        self.pdf_path = pdf_path
        self.password = password

    def extract(self, dpi: int = 300, threshold: int = 128):
        # Convert each page to an image
        images = convert_from_path(self.pdf_path, dpi=dpi, userpw=self.password)

        pages = []
        for i, img in enumerate(images):
            # Convert to grayscale
            gray_img = img.convert('L')
            # Binarize (black and white) with a threshold
            bw_img = gray_img.point(lambda x: 0 if x < threshold else 255, '1')
            text = pytesseract.image_to_string(bw_img, lang='eng')
            pages.append({
                "page_number": i + 1,
                "text": text.strip()
            })

        return pages