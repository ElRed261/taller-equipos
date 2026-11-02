"""Hashing y verificación de contraseñas.

argon2id es el estándar actual para guardar contraseñas: está pensado para ser
caro de calcular en memoria, que es justo lo que le quita valor a una base robada.
La sal viene dentro del propio hash, así que no hay que guardarla aparte.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

LARGO_MINIMO = 12

_hasher = PasswordHasher()


def hashear(clave: str) -> str:
    """Devuelve el hash que se guarda. La contraseña no se guarda nunca."""
    return _hasher.hash(clave)


def verificar(hash_guardado: str | None, clave: str) -> bool:
    """``True`` solo si la contraseña coincide con el hash guardado.

    Un hash corrupto o vacío devuelve ``False``: una fila a medio migrar no puede
    dejar entrar a nadie ni tumbar el arranque del programa.
    """
    if not hash_guardado or not clave:
        return False
    try:
        return _hasher.verify(hash_guardado, clave)
    except (VerificationError, InvalidHashError, ValueError):
        return False


def necesita_rehash(hash_guardado: str | None) -> bool:
    """``True`` si el hash se generó con parámetros más viejos que los actuales."""
    if not hash_guardado:
        return False
    try:
        return _hasher.check_needs_rehash(hash_guardado)
    except (VerificationError, InvalidHashError, ValueError):
        return False


def clave_aceptable(clave: str) -> str | None:
    """Motivo por el que la contraseña no sirve, o ``None`` si sirve.

    Se pide largo y nada más: las reglas de mayúsculas, números y símbolos
    empujan a la gente a contraseñas cortas y predecibles ("Password1!").
    """
    if len(clave) < LARGO_MINIMO:
        return f"La contraseña necesita al menos {LARGO_MINIMO} caracteres."
    if clave.strip() != clave:
        return "La contraseña no puede empezar ni terminar con espacios."
    if len(set(clave)) < 4:
        return "La contraseña es demasiado repetitiva."
    return None
