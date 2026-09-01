"""Documents API domain (s10).

Exposes the upload endpoint that bridges FastAPI ``UploadFile`` streams
to the :class:`app.services.rag.upload_service.UploadService` pipeline
shared with the CLI.

* ``POST /api/documents/upload`` — multipart upload (form fields
  ``pseudo``, ``subject`` + binary ``file``). Returns ``201`` on
  success, ``4xx/5xx`` mapped from :class:`UploadError` on failure.
"""
