"""
Handler para acortar URLs usando la API de Rebrandly
"""
import requests
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from urllib.parse import urlparse


class RebrandlyHandler:
    """Manejador para acortar URLs usando la API de Rebrandly"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.rebrandly.com/v1/links"
        self.headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json"
        }

    def es_url_valida(self, url: str) -> bool:
        """Valida si una URL tiene formato correcto"""
        try:
            resultado = urlparse(url)
            return all([resultado.scheme, resultado.netloc])
        except:
            return False

    def agregar_protocolo(self, url: str) -> str:
        """Agrega https:// si la URL no tiene protocolo"""
        if not url.startswith(('http://', 'https://')):
            return f"https://{url}"
        return url

    async def acortar_enlace(self, url: str, titulo: str = None) -> dict:
        """Acorta una URL usando la API de Rebrandly"""
        try:
            url = self.agregar_protocolo(url.strip())  # Preparar URL

            if not self.es_url_valida(url):
                return {"error": "❌ URL inválida. Formato: https://ejemplo.com"}

            datos = {"destination": url}  # Preparar datos para la API
            if titulo:
                datos["title"] = titulo[:50]  # Límite de caracteres

            response = requests.post(  # Realizar petición
                self.base_url,
                json=datos,
                headers=self.headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "short_url": data.get("shortUrl"),
                    "original_url": data.get("destination"),
                    "title": data.get("title", "Sin título"),
                    "clicks": data.get("clicks", 0)
                }
            elif response.status_code == 401:
                return {"error": "🔒 API key inválida"}
            elif response.status_code == 403:
                return {"error": "🚫 Sin permisos o límite de API alcanzado"}
            else:
                return {"error": f"⚠️ Error de API: {response.status_code}"}

        except requests.RequestException as e:
            logging.error(f"Error en petición Rebrandly: {e}")
            return {"error": "🌐 Error de conexión con Rebrandly"}
        except Exception as e:
            logging.error(f"Error inesperado en Rebrandly: {e}")
            return {"error": "❌ Error interno del servidor"}


async def comando_acortar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /acortar para crear enlaces cortos (solo administradores)"""
    from config import ADMIN_IDS, REBRANDLY_API_KEY  # Importación local

    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:  # Verificar permisos de administrador
        await update.message.reply_text(
            "🚫 **Acceso denegado**\n"
            "Este comando está restringido para administradores",
            parse_mode='Markdown'
        )
        return

    if not context.args:  # Mostrar uso del comando
        await update.message.reply_text(
            "📖 **Uso del comando:**\n\n"
            "`/acortar <URL> [título]`\n\n"
            "**Ejemplos:**\n"
            "• `/acortar https://google.com`\n"
            "• `/acortar youtube.com Mi video favorito`\n"
            "• `/acortar github.com/usuario/repo Repositorio`",
            parse_mode='Markdown'
        )
        return

    url = context.args[0]  # Extraer URL y título opcional
    titulo = " ".join(context.args[1:]) if len(context.args) > 1 else None

    if not REBRANDLY_API_KEY:  # Verificar API key
        await update.message.reply_text(
            "⚙️ **Error de configuración**\n"
            "API key de Rebrandly no configurada",
            parse_mode='Markdown'
        )
        return

    mensaje_proceso = await update.message.reply_text("🔄 Acortando enlace...")  # Mensaje de procesamiento

    rebrandly = RebrandlyHandler(REBRANDLY_API_KEY)  # Crear instancia y procesar
    resultado = await rebrandly.acortar_enlace(url, titulo)

    if "error" in resultado:  # Procesar resultado
        await mensaje_proceso.edit_text(resultado["error"])
    else:
        respuesta = (
            f"✅ **Enlace acortado exitosamente**\n\n"
            f"🔗 **Original:** `{resultado['original_url']}`\n"
            f"🎯 **Corto:** `{resultado['short_url']}`\n"
            f"📊 **Clicks:** {resultado['clicks']}"
        )

        if resultado.get('title') != "Sin título":
            respuesta += f"\n📝 **Título:** {resultado['title']}"

        await mensaje_proceso.edit_text(respuesta, parse_mode='Markdown')


def register_rebrandly_handler(application) -> None:
    """Registra el handler de Rebrandly en la aplicación"""
    try:
        from config import REBRANDLY_API_KEY

        if not REBRANDLY_API_KEY or REBRANDLY_API_KEY.strip() == "":  # Validar que existe la API key
            logging.warning("⚠️ API key de Rebrandly no configurada en .env - Handler deshabilitado")
            logging.info("💡 Agrega REBRANDLY_API_KEY=tu_api_key en el archivo .env")
            return

        application.add_handler(CommandHandler("acortar", comando_acortar))  # Registrar comando

    except ImportError as e:
        logging.error(f"❌ Error importando config para Rebrandly: {e}")
    except Exception as e:
        logging.error(f"❌ Error registrando handler Rebrandly: {e}")