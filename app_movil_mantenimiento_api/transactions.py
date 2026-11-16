from functools import wraps
import secrets
import time

from django.db import OperationalError
from rest_framework.exceptions import APIException


class DatabaseBusy(APIException):
    status_code = 503
    default_detail = "El sistema está ocupado. Intenta guardar de nuevo."


def retry_transaction(view):
    """Retry only after the entire atomic view has rolled back a lock conflict."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        for attempt in range(4):
            try:
                return view(*args, **kwargs)
            except OperationalError as exc:
                if not exc.args or exc.args[0] not in (1205, 1213):
                    raise
                if attempt == 3:
                    raise DatabaseBusy() from exc
                time.sleep((20 * (attempt + 1) + secrets.randbelow(30)) / 1000)
    return wrapped
