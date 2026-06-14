import secrets
import string
from typing import List, Set


class SecureKeyGenerator:
    """Generador de claves seguras: contraseñas, PINs y tokens"""

    def __init__(self):
        # Patrones inseguros para PINs y tokens
        self.pin_patrones_inseguros: Set[str] = {
            "0000", "1111", "2222", "3333", "4444", "5555", "6666", "7777", "8888", "9999",
            "1234", "4321", "0123", "3210", "2468", "8642", "1357", "7531"
        }

        self.token_patrones_inseguros: Set[str] = {
            "000000", "111111", "222222", "333333", "444444", "555555",
            "666666", "777777", "888888", "999999", "123456", "654321",
            "012345", "543210", "246810", "108642", "135792", "297531"
        }

    def generar_contraseña_segura(self, longitud: int = 12) -> str:
        """Genera una contraseña segura de 12 caracteres por defecto"""

        # Conjuntos de caracteres
        mayusculas = string.ascii_uppercase
        minusculas = string.ascii_lowercase
        numeros = string.digits
        simbolos = "!@#$%&*+-=?_"  # Símbolos seguros y compatibles

        # Patrones a evitar
        patrones_inseguros = ["123", "abc", "qwe", "asd", "zxc", "qwerty", "asdf"]

        while True:
            # Asegurar al menos un carácter de cada tipo
            contraseña = [
                secrets.choice(mayusculas),  # Al menos 1 mayúscula
                secrets.choice(minusculas),  # Al menos 1 minúscula
                secrets.choice(numeros),  # Al menos 1 número
                secrets.choice(simbolos)  # Al menos 1 símbolo
            ]

            # Completar con caracteres aleatorios
            todos_caracteres = mayusculas + minusculas + numeros + simbolos
            for _ in range(longitud - 4):
                contraseña.append(secrets.choice(todos_caracteres))

            # Mezclar la contraseña
            secrets.SystemRandom().shuffle(contraseña)
            contraseña_final = ''.join(contraseña)

            # Verificar que no contenga patrones inseguros
            if not self._contiene_patrones_inseguros(contraseña_final.lower(), patrones_inseguros):
                return contraseña_final

    def generar_pin_seguro(self, longitud: int = 4) -> str:
        """Genera un PIN seguro de 4 dígitos por defecto"""

        intentos = 0
        max_intentos = 100

        while intentos < max_intentos:
            pin = ''.join([secrets.choice(string.digits) for _ in range(longitud)])

            # Verificar que no sea un patrón inseguro
            if pin not in self.pin_patrones_inseguros and not self._es_secuencia_simple(pin):
                return pin

            intentos += 1

        # Si no se encuentra un PIN seguro, generar uno más complejo
        return self._generar_pin_complejo(longitud)

    def generar_token_acceso(self, longitud: int = 6) -> str:
        """Genera un token de acceso seguro de 6 dígitos por defecto"""

        intentos = 0
        max_intentos = 100

        while intentos < max_intentos:
            token = ''.join([secrets.choice(string.digits) for _ in range(longitud)])

            # Verificar que no sea un patrón inseguro
            if token not in self.token_patrones_inseguros and not self._es_secuencia_simple(token):
                return token

            intentos += 1

        # Si no se encuentra un token seguro, generar uno más complejo
        return self._generar_token_complejo(longitud)

    def _contiene_patrones_inseguros(self, texto: str, patrones: List[str]) -> bool:
        """Verifica si el texto contiene algún patrón inseguro"""
        return any(patron in texto for patron in patrones)

    def _es_secuencia_simple(self, numero: str) -> bool:
        """Verifica si es una secuencia numérica simple (ascendente o descendente)"""
        if len(numero) < 3:
            return False

        # Verificar secuencia ascendente
        ascendente = all(int(numero[i]) == int(numero[i - 1]) + 1 for i in range(1, len(numero)))
        # Verificar secuencia descendente
        descendente = all(int(numero[i]) == int(numero[i - 1]) - 1 for i in range(1, len(numero)))

        return ascendente or descendente

    def _generar_pin_complejo(self, longitud: int) -> str:
        """Genera un PIN más complejo cuando los métodos normales fallan"""
        # Usar una estrategia diferente: números no consecutivos
        digitos_disponibles = list(string.digits)
        pin = []

        for i in range(longitud):
            # Evitar repetir el dígito anterior
            if i > 0:
                digitos_filtrados = [d for d in digitos_disponibles if d != pin[-1]]
                pin.append(secrets.choice(digitos_filtrados))
            else:
                pin.append(secrets.choice(digitos_disponibles))

        return ''.join(pin)

    def _generar_token_complejo(self, longitud: int) -> str:
        """Genera un token más complejo cuando los métodos normales fallan"""
        # Usar la misma estrategia que el PIN complejo
        return self._generar_pin_complejo(longitud)

    def generar_conjunto_completo(self) -> dict:
        """Genera un conjunto completo de claves: contraseña, PIN y token"""
        return {
            'contraseña': self.generar_contraseña_segura(),
            'pin': self.generar_pin_seguro(),
            'token': self.generar_token_acceso()
        }