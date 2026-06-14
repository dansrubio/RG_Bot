"""
Servicio para gestionar la publicación de artículos en Telegraph para Steam.
Abstrae la inicialización y construcción de páginas con requisitos e imágenes.
"""

import html
import logging
import re

logger = logging.getLogger(__name__)

try:
    from telegraph import Telegraph
    TELEGRAPH_AVAILABLE = True
except ImportError:
    TELEGRAPH_AVAILABLE = False
    Telegraph = None


class SteamTelegraphService:
    def __init__(self):
        self.client = None
        self.initialized = False

    def init_client(self) -> bool:
        """Inicializa la cuenta de Telegraph una sola vez."""
        if not TELEGRAPH_AVAILABLE:
            logger.warning("⚠️ Telegraph no está instalado en el entorno.")
            return False
        
        if self.initialized:
            return True
        
        try:
            self.client = Telegraph()
            self.client.create_account(short_name="Rednite_bot - @Refugio_Gamer")
            self.initialized = True
            logger.info
            return True
        except Exception:
            try:
                self.client = Telegraph()
                self.initialized = True
                logger.info
                return True
            except Exception as e:
                logger.error(f"❌ Error crítico al inicializar Telegraph de Steam: {e}")
                return False

    def clean_html(self, text: str) -> str:
        """Limpia tags HTML, decodifica entidades y formatea las secciones de texto de Steam."""
        if not text:
            return ""
        
        text = html.unescape(text)
        text = re.sub(r'(<br\s*/?>)+', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        lines = [line.strip() for line in text.split('\n')]
        
        formatted_lines = []
        for line in lines:
            if re.match(r'^(características principales|requisitos del sistema|features|configuración):', line, re.IGNORECASE):
                formatted_lines.append("")
                formatted_lines.append(line)
            else:
                formatted_lines.append(line)
                
        text = '\n'.join(formatted_lines)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def create_requirements_page(self, game_name: str, full_data: dict, requirements: dict, screenshots_urls: list = None) -> str | None:
        """Crea un artículo estructurado en Telegraph con todos los metadatos extraíbles de Steam."""
        if not self.initialized and not self.init_client():
            return None
        
        try:
            content = []
            
            header_image = full_data.get('header_image')
            if header_image:
                content.append(f"<img src='{header_image}' />")
            content.append(f"<p><strong>{html.escape(game_name)}</strong></p><br>")
            
            content.append("<p><strong>⚙️ Requisitos del Sistema</strong></p>")
            if requirements:
                has_minimum = requirements.get('minimum') and requirements['minimum'].strip()
                has_recommended = requirements.get('recommended') and requirements['recommended'].strip()
                
                if has_minimum:
                    minimum_html = requirements['minimum'].replace('\n', '<br>')
                    content.append("<p><strong>🔹 Requisitos Mínimos:</strong></p>")
                    content.append(f"<p>{minimum_html}</p><br>")
                
                if has_recommended:
                    recommended_html = requirements['recommended'].replace('\n', '<br>')
                    content.append("<p><strong>🔹 Requisitos Recomendados:</strong></p>")
                    content.append(f"<p>{recommended_html}</p><br>")
            else:
                content.append("<p><em>No se especificaron requisitos técnicos detallados para este título.</em></p><br>")
            
            content.append("<hr>")

            if screenshots_urls:
                content.append("<p><strong>📸 Capturas de Pantalla</strong></p>")
                for screenshot_url in screenshots_urls:
                    content.append(f"<img src='{screenshot_url}' />")
                content.append("<br><hr>")
            
            content.append("<p><strong>📋 Ficha Técnica e Información General</strong></p>")
            
            def _join_field(field_key):
                items = full_data.get(field_key, [])
                return ", ".join([i.get('description', i) if isinstance(i, dict) else str(i) for i in items if i])

            platforms = [p for p in ['Windows', 'macOS', 'Linux'] if full_data.get('platforms', {}).get(p.lower().replace('macos', 'mac'))]
            developers = _join_field('developers') or "Desconocido"
            publishers = _join_field('publishers') or "Desconocido"
            release_date = full_data.get('release_date', {}).get('date', 'No disponible').strip()
            genres = [g.get('description') for g in full_data.get('genres', []) if isinstance(g, dict)]
            metacritic = full_data.get('metacritic', {}).get('score')
            
            controller_support = full_data.get('controller_support', 'No')
            controller_text = "Completo" if controller_support == 'full' else ("Parcial" if controller_support == 'partial' else 'No')
            
            achievements_dict = full_data.get('achievements', {})
            total_achievements = achievements_dict.get('total', 0) if isinstance(achievements_dict, dict) else 0
            
            price_overview = full_data.get('price_overview', {})
            if price_overview and isinstance(price_overview, dict):
                price_text = price_overview.get('final_formatted', 'Gratis o No Disponible')
            else:
                price_text = "Gratis" if full_data.get('is_free') else "No disponible"

            content.append(f"<p>📅 <strong>Lanzamiento:</strong> {html.escape(release_date)}</p>")
            content.append(f"<p>👨‍💻 <strong>Desarrollador:</strong> {html.escape(developers)}</p>")
            content.append(f"<p>🏢 <strong>Editor:</strong> {html.escape(publishers)}</p>")
            if platforms:
                content.append(f"<p>🖥️ <strong>Plataformas:</strong> {' • '.join(platforms)}</p>")
            if genres:
                content.append(f"<p>🎲 <strong>Géneros:</strong> {html.escape(', '.join(genres))}</p>")
            if metacritic:
                content.append(f"<p>⭐ <strong>Metacritic:</strong> {metacritic}/100</p>")
            content.append(f"<p>🎮 <strong>Compatibilidad de Mando:</strong> {controller_text}</p>")
            if total_achievements > 0:
                content.append(f"<p>🏆 <strong>Logros de Steam:</strong> {total_achievements} disponibles</p>")
            content.append(f"<p>💰 <strong>Precio Actual:</strong> {html.escape(price_text)}</p>")
            content.append("<br>")

            supported_languages = full_data.get('supported_languages')
            if supported_languages:
                content.append("<p><strong>🗣️ Idiomas Disponibles</strong></p>")
                clean_languages = html.unescape(supported_languages).replace('<strong>*', ' (Voces: <strong>')
                content.append(f"<p><em>{clean_languages}</em></p><br>")

            categories = [c.get('description') for c in full_data.get('categories', []) if isinstance(c, dict)]
            if categories:
                content.append("<p><strong>🏷️ Características y Modalidades:</strong></p>")
                content.append(f"<blockquote>{' • '.join(categories)}</blockquote><br>")

            description = self.clean_html(full_data.get('detailed_description', full_data.get('about_the_game', full_data.get('short_description', ''))))
            if description:
                content.append("<p><strong>📖 Resumen del Juego</strong></p>")
                description_html = html.escape(description).replace('\n', '<br>')
                content.append(f"<p>{description_html}</p><br>")
            
            content.append("<hr><p><strong>ℹ️ Información de Enlaces Externos</strong></p>")
            
            size_mb = full_data.get('size_on_disk')
            if size_mb:
                content.append(f"<p><strong>💾 Espacio aproximado en disco:</strong> {size_mb / 1024:.2f} GB</p>")
            
            steam_appid = full_data.get('steam_appid')
            if steam_appid:
                content.append(f"<p><strong>🔗 App ID de Steam:</strong> <code>{steam_appid}</code> — <a href='https://store.steampowered.com/app/{steam_appid}'>Abrir Tienda Oficial</a></p>")
            
            website = full_data.get('website')
            if website:
                content.append(f"<p><strong>🌐 Sitio Web Oficial:</strong> <a href='{website}'>Visitar enlace</a></p>")
            
            html_content = "".join(content)
            
            response = self.client.create_page(
                title=f"{game_name} - Ficha Técnica Completa",
                html_content=html_content,
                author_name="Rednite Bot - @Refugio_Gamer"
            )
            
            return response.get('url') if isinstance(response, dict) else None
            
        except Exception as e:
            logger.error(f"❌ Error al crear página en Telegraph de Steam: {e}")
            return None

steam_telegraph_service = SteamTelegraphService()