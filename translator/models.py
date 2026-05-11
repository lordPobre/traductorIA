import uuid
from django.db import models

class Document(models.Model):
    class Status(models.TextChoices):
        UPLOADED = 'UPLOADED', 'Subido / Pendiente'
        EXTRACTING = 'EXTRACTING', 'Extrayendo Texto y OCR'
        TRANSLATING = 'TRANSLATING', 'Traduciendo Bloques'
        GENERATING = 'GENERATING', 'Generando Nuevo PDF'
        COMPLETED = 'COMPLETED', 'Completado'
        FAILED = 'FAILED', 'Fallido'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_file = models.FileField(upload_to='uploads/pdfs/original/')
    translated_file = models.FileField(upload_to='downloads/pdfs/translated/', null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
    )
    total_pages = models.IntegerField(default=0)
    processed_pages = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        filename = self.original_file.name.split('/')[-1] if self.original_file else 'Sin archivo'
        return f"{filename} - {self.get_status_display()} ({self.processed_pages}/{self.total_pages})"

    @property
    def progress_percentage(self):
        if self.total_pages == 0:
            return 0
        return int((self.processed_pages / self.total_pages) * 100)