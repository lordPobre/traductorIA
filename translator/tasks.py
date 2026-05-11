import fitz
import pytesseract
from PIL import Image
import io
import requests
import re
import os
from datetime import timedelta
from django.utils import timezone
from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from fpdf import FPDF
from .models import Document

if settings.TESSERACT_CMD_PATH:
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD_PATH

def translate_text_with_deepl(text, target_lang='ES'):
    if not text.strip(): return "" 
    headers = {'Authorization': f'DeepL-Auth-Key {settings.DEEPL_API_KEY}', 'Content-Type': 'application/json'}
    data = {'text': [text], 'target_lang': target_lang, 'source_lang': 'EN'}
    response = requests.post(settings.DEEPL_API_URL, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()['translations'][0]['text']
    raise Exception(f"Error DeepL: {response.status_code} - {response.text}")

@shared_task
def process_pdf_translation(document_id, target_lang='ES'):
    try:
        doc = Document.objects.get(id=document_id)
        doc.status = Document.Status.EXTRACTING
        doc.save()

        pdf_path = doc.original_file.path
        pdf_document = fitz.open(pdf_path)
        doc.total_pages = len(pdf_document)
        doc.save()

        # --- 1. EXTRACCIÓN (NATIVO + OCR) Y LIMPIEZA ---
        full_document_text = ""
        pending_sentence = ""

        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            page_text_elements = []

            # A) TEXTO NATIVO (Por si el PDF tiene partes digitales)
            blocks = page.get_text("blocks")
            for b in blocks:
                if b[6] == 0:
                    page_text_elements.append(b[4])

            # B) TEXTO ESCANEADO (Vital para tu documento de 1963)
            for img in page.get_images(full=True):
                xref = img[0]
                base_image = pdf_document.extract_image(xref)
                image = Image.open(io.BytesIO(base_image["image"])).convert('L')
                ocr_text = pytesseract.image_to_string(image, lang='eng')
                page_text_elements.append(ocr_text)

            # C) FILTRADO Y UNIÓN DE ORACIONES
            for text_block in page_text_elements:
                clean_text = re.sub(r'-\n+', '', text_block).replace('\n', ' ').strip()
                
                # Ignoramos encabezados, números de página cortos y sellos sin letras
                if "OFFICIAL USE ONLY" in clean_text or re.match(r'^-\s*\d+\s*-$', clean_text): continue
                if len(clean_text) < 15 and not re.search(r'[a-z]', clean_text): continue
                
                if not clean_text: continue

                # Unimos con lo que quedó colgando de la página anterior
                if pending_sentence:
                    clean_text = pending_sentence + " " + clean_text
                    pending_sentence = ""

                # Si termina en puntuación, es un párrafo completo. Si no, lo guardamos para el siguiente bloque.
                if clean_text.endswith(('.', ':', '?', ')', '"')):
                    full_document_text += f"{clean_text}\n\n"
                else:
                    pending_sentence = clean_text

            doc.processed_pages = page_num + 1
            doc.save()

        if pending_sentence: full_document_text += f"{pending_sentence}\n\n"
        full_document_text = re.sub(r' +', ' ', full_document_text)

        # --- 2. DIVISIÓN INTELIGENTE (CHUNKING) ---
        paragraphs = full_document_text.split('\n\n')
        text_chunks, current_chunk = [], ""
        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) > 3000:
                text_chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"
            else:
                current_chunk += paragraph + "\n\n"
        if current_chunk: text_chunks.append(current_chunk.strip())

        # --- 3. TRADUCCIÓN ---
        doc.status = Document.Status.TRANSLATING
        doc.processed_pages = 0
        doc.save()
        
        translated_full_text = ""
        for index, chunk in enumerate(text_chunks):
            if chunk.strip():
                translated_full_text += translate_text_with_deepl(chunk, target_lang=target_lang) + "\n\n"
            doc.processed_pages = int(((index + 1) / len(text_chunks)) * doc.total_pages)
            doc.save()

        # --- 4. GENERACIÓN DE PDF LIMPIO (FORMATO LIBRO) ---
        doc.status = Document.Status.GENERATING
        doc.save()
        
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()
        
        pdf.set_font("helvetica", style="B", size=16)
        pdf.set_text_color(41, 128, 185)
        pdf.cell(0, 10, "Documento Traducido", ln=True, align="C", border="B")
        pdf.ln(10)
        
        pdf.set_font("helvetica", size=11)
        pdf.set_text_color(40, 40, 40)
        
        safe_text = translated_full_text.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 7, text=safe_text, align="J")
            
        pdf_bytes = bytes(pdf.output())
        doc.translated_file.save(f"documento_traducido_{doc.id}.pdf", ContentFile(pdf_bytes))
        
        doc.status = Document.Status.COMPLETED
        doc.processed_pages = doc.total_pages
        doc.save()

    except Exception as e:
        doc.status = Document.Status.FAILED
        doc.error_message = str(e)
        doc.save()
        print(f"Error crítico: {str(e)}")

# ==========================================
# MANTENIMIENTO: LIMPIEZA AUTOMÁTICA
# ==========================================
@shared_task
def cleanup_old_documents():
    # Calculamos la fecha y hora exacta de hace 24 horas
    time_threshold = timezone.now() - timedelta(hours=24)
    
    # Filtramos los documentos más antiguos que esa fecha
    old_docs = Document.objects.filter(created_at__lt=time_threshold)
    count = 0
    
    for doc in old_docs:
        # 1. Borramos el archivo original físico
        if doc.original_file and os.path.isfile(doc.original_file.path):
            os.remove(doc.original_file.path)
            
        # 2. Borramos el archivo traducido físico
        if doc.translated_file and os.path.isfile(doc.translated_file.path):
            os.remove(doc.translated_file.path)
            
        # 3. Borramos el registro de la base de datos
        doc.delete()
        count += 1
        
    print(f"Limpieza completada: {count} documentos viejos eliminados.")
    return f"{count} eliminados"