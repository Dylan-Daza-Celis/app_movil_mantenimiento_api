from app_movil_mantenimiento_api.models import *
import json
import requests
import datetime
import secrets
import string
from urllib.parse import urlparse
from django.conf import settings

class DataUtils:

    @staticmethod
    def generate_frontend_enc_key():
        key_1 = DataUtils.randomNumber(4)
        key_2 = DataUtils.randomNumber(4)
        key_3 = DataUtils.randomNumber(4)
        key_4 = DataUtils.randomNumber(4)

        key = []
        key.append(key_1)
        key.append(key_2)
        key.append(key_3)
        key.append(key_4)
        str_key = ",".join(key)

        return str_key

    @staticmethod
    def randomString(stringLength=10):
        """Generate a random string of fixed length """
        letters = string.ascii_lowercase
        return ''.join(secrets.choice(letters) for i in range(stringLength))

    @staticmethod
    def randomNumber(numberLength=10):
        """Generate a random number of fixed length """
        digits = string.digits
        return ''.join(secrets.choice(digits) for i in range(numberLength))

    @staticmethod
    def get_file_extension(mime_type):
        if mime_type:
            if mime_type=="video/mp4":
                return ".mp4"
            elif mime_type=="video/x-m4v":
                return ".m4v"
            elif mime_type=="video/webm":
                return ".webm"
        else:
            return ""

    @staticmethod
    def get_file_mimetype(file_name):
        if file_name:
            if ".mp4" in file_name:
                return "video/mp4"
            elif ".m4v" in file_name:
                return "video/x-m4v"
            elif ".webm" in file_name:
                return "video/webm"
        else:
            return ""


    @staticmethod
    def is_url(text):
        return text.startswith('http://') or text.startswith('https://')

    @staticmethod
    def is_url_image(image_url):
        parsed = urlparse(image_url)
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.hostname not in getattr(settings, 'IMAGE_HOST_ALLOWLIST', ()):
            return False
        image_formats = ("image/png", "image/jpeg", "image/jpg")
        try:
            with requests.head(image_url, timeout=5, allow_redirects=False) as response:
                return response.ok and response.headers.get('content-type', '').split(';')[0].strip().lower() in image_formats
        except requests.RequestException:
            return False

    @staticmethod
    def getUrl(request):

        absolute_uri = request.build_absolute_uri()
        full_path = request.get_full_path()

        url = absolute_uri
        cut = absolute_uri.find(full_path)
        if cut > 0:
            url = absolute_uri.replace(full_path,"")

        return url
