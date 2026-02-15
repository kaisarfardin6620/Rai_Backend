from rest_framework.views import exception_handler
from rest_framework.response import Response
import logging

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        logger.error(f"Unhandled Exception in {context['view'].__class__.__name__}: {exc}", exc_info=True)
        return Response(
            {"message": "An unexpected error occurred. Please try again later."},
            status=500
        )

    if response is not None:
        data = response.data
        if isinstance(data, list):
            response.data = {"errors": data}
        if isinstance(data, dict):
            pass
            
    return response