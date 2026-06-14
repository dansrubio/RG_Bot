"""
Servicio para gestionar la publicación de artículos en Telegraph para juegos de IGDB.
Soporta de manera dinámica múltiples plataformas (PS4, PC, Switch) y múltiples capturas de pantalla.
"""

import html
import logging
import re
from telegraph import Telegraph

logger = logging.getLogger(__name__)

class IGDBTelegraphService:
    def __init__(self):
        self.client = None
        self.initialized = False

    def init_client(self) -> bool:
        """Inicializa la cuenta de Telegraph una sola vez."""
        if self.initialized:
            return True
        try:
            self.client = Telegraph()
            self.client.create_account(short_name="RG_IGDBBot")
            self.initialized = True
            return True
        except Exception as e:
            logger.error(f"❌ Error al inicializar Telegraph IGDB: {e}")
            return False

    def clean_html(self, text: str) -> str:
        if not text:
            return ""
        text = html.unescape(text)
        text = re.sub(r'(<br\s*/?>)+', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        lines = [line.strip() for line in text.split('\n')]
        
        formatted_lines = []
        for line in lines:
            if re.match(r'^(características principales|features|detalles|contenido):', line, re.IGNORECASE):
                formatted_lines.append("")
                formatted_lines.append(line)
            else:
                formatted_lines.append(line)
                
        text = '\n'.join(formatted_lines)
        return re.sub(r'\n{3,}', '\n\n', text).strip()

    def create_igdb_page(self, game_name: str, full_data: dict, plataforma_tag: str, screenshots_urls: list = None) -> str | None:
        """Crea un artículo estructurado en Telegraph con datos extraídos de IGDB."""
        if not self.initialized and not self.init_client():
            return None
        
        try:
            content = []
            
            # HEADER / BANNER PRINCIPAL
            bg_image = full_data.get('background_image')
            if bg_image:
                content.append(f"<img src='{bg_image}' />")
            content.append(f"<p><strong>{html.escape(game_name)} ({plataforma_tag})</strong></p><br>")
            
            # ==========================================
            # 1. INFORMACIÓN TÉCNICA E INSTALACIÓN
            # ==========================================
            content.append(f"<p><strong>⚙️ Especificaciones e Información de {plataforma_tag}</strong></p>")
            content.append("<p><strong>🔹 Requisitos de Instalación:</strong></p>")
            
            if plataforma_tag == "PC":
                content.append("<p>• <strong>Plataforma:</strong> PC (Windows / Linux / macOS)<br>")
                content.append("• <strong>Distribución:</strong> Digital (Steam / Epic Games / GOG)<br>")
                content.append("• <strong>Almacenamiento:</strong> Se sugiere revisar las especificaciones del launcher final; guarde espacio suficiente en SSD para mejor rendimiento.</p><br>")
            elif plataforma_tag == "Nintendo Switch":
                content.append("<p>• <strong>Plataforma:</strong> Nintendo Switch (Lite / OLED)<br>")
                content.append("• <strong>Formato:</strong> Cartucho Físico / Digital eShop<br>")
                content.append("• <strong>Memoria:</strong> Requiere espacio libre en memoria interna o tarjeta MicroSD para parches obligatorios.</p><br>")
            else:
                content.append(f"<p>• <strong>Plataforma:</strong> {plataforma_tag}<br>")
                content.append("• <strong>Formato:</strong> Digital / Disco Físico Blu-Ray<br>")
                content.append("• <strong>Espacio mínimo requerido:</strong> Se recomienda disponer de al menos 40-50 GB libres en el HDD/SSD para la instalación base y parches acumulativos.</p><br>")
            
            content.append("<hr>")

            # ==========================================
            # 2. MÚLTIPLES CAPTURAS DE PANTALLA (ACTUALIZADO)
            # ==========================================
            if screenshots_urls:
                content.append("<p><strong>📸 Capturas de Pantalla</strong></p>")
                for shot_url in screenshots_urls:
                    content.append(f"<img src='{shot_url}' />")
                content.append("<br><hr>")
            
            # ==========================================
            # 3. FICHA TÉCNICA GENERAL
            # ==========================================
            content.append("<p><strong>📋 Ficha Técnica</strong></p>")
            
            release_date = full_data.get('released', 'No disponible')
            metacritic = full_data.get('metacritic', 'No evaluado')
            developers = ", ".join([d.get('name') for d in full_data.get('developers', [])]) or "Desconocido"
            publishers = ", ".join([p.get('name') for p in full_data.get('publishers', [])]) or "Desconocido"
            genres = ", ".join([g.get('name') for g in full_data.get('genres', [])]) or "No definidos"

            content.append(f"<p>📅 <strong>Lanzamiento:</strong> {html.escape(release_date)}</p>")
            content.append(f"<p>👨‍💻 <strong>Desarrollador:</strong> {html.escape(developers)}</p>")
            content.append(f"<p>🏢 <strong>Editor:</strong> {html.escape(publishers)}</p>")
            content.append(f"<p>🎲 <strong>Géneros:</strong> {html.escape(genres)}</p>")
            content.append(f"<p>⭐ <strong>Calificación de la Comunidad:</strong> {metacritic}/100</p>")
            content.append("<br>")

            # ==========================================
            # 4. DESCRIPCIÓN DETALLES
            # ==========================================
            description = self.clean_html(full_data.get('description_raw', ''))
            if description:
                content.append("<p><strong>📖 Resumen del Juego</strong></p>")
                description_html = html.escape(description).replace('\n', '<br>')
                content.append(f"<p>{description_html}</p><br>")
            
            # Pie de página
            content.append("<hr><p><strong>ℹ️ Información Adicional</strong></p>")
            website = full_data.get('website')
            if website:
                content.append(f"<p>🌐 <strong>Enlace de Referencia:</strong> <a href='{website}'>Visitar enlace oficial</a></p>")

            html_content = "".join(content)
            
            response = self.client.create_page(
                title=f"{game_name} - Ficha Técnica de {plataforma_tag}",
                html_content=html_content,
                author_name="Rednite Bot - @Refugio_Gamer"
            )
            
            return response.get('url') if isinstance(response, dict) else None
            
        except Exception as e:
            logger.error(f"❌ Error al crear página en Telegraph de IGDB: {e}")
            return None

igdb_telegraph_service = IGDBTelegraphService()