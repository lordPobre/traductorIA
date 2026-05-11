# backend/translator/views.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from .models import Document
from .tasks import process_pdf_translation


@csrf_exempt 
def upload_document(request):
    if request.method == 'POST':
        pdf_file = request.FILES.get('file')
        
        # NUEVO: Capturamos el idioma deseado (por defecto será Español 'ES')
        target_lang = request.POST.get('target_lang', 'ES') 
        
        if not pdf_file:
            return JsonResponse({'error': 'No se proporcionó ningún archivo'}, status=400)
            
        if not pdf_file.name.lower().endswith('.pdf'):
            return JsonResponse({'error': 'El archivo debe ser un PDF'}, status=400)

        doc = Document.objects.create(
            original_file=pdf_file,
            total_pages=0 
        )
        
        # ACTUALIZADO: Le pasamos el idioma a Celery
        process_pdf_translation.delay(doc.id, target_lang)
        
        return JsonResponse({
            'message': 'Documento subido correctamente.',
            'document_id': str(doc.id),
            'status': doc.status
        }, status=201)

    return JsonResponse({'error': 'Método no permitido. Usa POST.'}, status=405)

def get_document_status(request, document_id):
    if request.method == 'GET':
        doc = get_object_or_404(Document, id=document_id)
        
        # Construimos la respuesta
        data = {
            'status': doc.status,
            'progress': doc.progress_percentage, # Usamos la propiedad que creamos en models.py
            'download_url': None
        }
        
        # Si el documento está completado y tiene archivo, armamos la URL completa
        if doc.status == Document.Status.COMPLETED and doc.translated_file:
            data['download_url'] = request.build_absolute_uri(doc.translated_file.url)
            
        # Si falló, enviamos el error
        if doc.status == Document.Status.FAILED:
            data['error'] = doc.error_message

        return JsonResponse(data)
    
def get_status(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    return JsonResponse({
        'status': doc.status,
        'status_display': doc.get_status_display(),
        'progress': doc.progress_percentage,
        'translated_file_url': doc.translated_file.url if doc.translated_file else None,
        'error_message': doc.error_message
    })