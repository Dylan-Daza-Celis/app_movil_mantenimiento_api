from rest_framework.exceptions import ValidationError
import re


def ticket_id(value):
    if not isinstance(value, str) or re.fullmatch(r'MANT-[0-9]{9}', value) is None:
        raise ValidationError({'detail': 'Selecciona un folio válido, por ejemplo MANT-261116001.'})
    return value


def positive_id(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).isascii() or not str(value).isdigit():
        raise ValidationError({"detail": "Selecciona un identificador válido."})
    result = int(value)
    if result < 1 or result > 9223372036854775807:
        raise ValidationError({"detail": "Selecciona un identificador válido."})
    return result
