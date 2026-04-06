"""Instancia compartida del rate limiter. Importar desde aquí para evitar referencias circulares."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
