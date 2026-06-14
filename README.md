# 🎮 Rednite Bot — Refugio Gamer

Bot de Telegram modular construido con `python-telegram-bot` v20+, MongoDB y Telethon.
Gestiona un catálogo de juegos con entrega automática de archivos, sistema de solicitudes, publicación en canales y múltiples almacenes independientes.

---

## ✨ Funcionalidades principales

| Módulo | Descripción |
|---|---|
| 📦 **Catálogo multi-almacén** | PC, PS4, Switch, Canaima y Audiovisuales con rutas independientes |
| 🔑 **Tokens seguros** | Generación atómica con contador MongoDB, imposibles de adivinar |
| 📤 **Entrega silenciosa** | Reenvío de archivos por privado sin exponer el almacén de origen |
| 🎫 **Tickets de solicitudes** | Sistema de tickets con panel de admin y estados (activo/completado/rechazado) |
| 🔍 **Búsqueda en tiempo real** | Por nombre o texto indexado con paginación inline |
| 📢 **Publicación automática** | Confirmación por botón, extracción de metadatos y limpieza de caption |
| 🤖 **Userbot indexador** | Escanea el almacén con Telethon y crea elementos automáticamente |
| 🎮 **APIs externas** | Steam, IGDB (PS4/Switch), RAWG, PokeAPI, YGOPRODeck, GamerPower |
| 🆓 **Juegos gratis** | Monitor de Epic Games, GOG y Steam con deduplicación en MongoDB |
| 🛡️ **Verificación de canales** | El usuario debe estar en los canales configurados para recibir archivos |
| 📊 **Estadísticas** | Usuarios, elementos, solicitudes por almacén con Top 100 paginado |
| 🔔 **Notificaciones masivas** | Wizard de 4 pasos para enviar mensajes a todos los usuarios registrados |
| 🏷️ **Recomendaciones** | Los admins pueden destacar elementos con `/recomendar` |
| 🎲 **Pokédex interactiva** | Ficha, evoluciones, debilidades, encuentros y movimientos |
| 🃏 **Yu-Gi-Oh!** | Búsqueda de cartas, arquetipos, sets y precios |
| ⚙️ **Panel de moderación** | Gestión de moderadores en caliente sin reiniciar |
| 💾 **Backup / Restore** | Export e import completo de MongoDB vía Telegram |

---

## ⚙️ Configuración

### 1. Clonar e instalar dependencias

```bash
git clone https://github.com/tu-usuario/rednite-bot.git
cd rednite-bot
pip install -r requirements.txt
```

### 2. Crear `config.env`

### 3. Ejecutar

```bash
python main.py
```

---

## 🤖 Comandos disponibles

### Usuarios
| Comando | Descripción |
|---|---|
| `/start` | Bienvenida o entrega de elemento por token |
| `/catalogo` | Navegación A-Z del catálogo paginado |
| `/juego_aleatorio` | Elemento aleatorio del sistema |
| `/top_all` | Top 100 global por usuarios únicos |
| `/top_pc` `/top_ps4` `/top_switch` | Top 100 por almacén |
| `/recomendados` | Lista de elementos destacados |
| `/solicitudes` | Ver tus tickets activos |
| `/pokemon` `/pkm` | Pokédex interactiva |
| `/carta` `/yugioh` | Búsqueda de cartas Yu-Gi-Oh! |
| `/game` | Búsqueda en Steam |
| `/juegosgratis` | Juegos gratuitos actuales |
| `/wow_token` | Precio del token de World of Warcraft |
| `/random` | Generador de contraseñas seguras |
| `/donate` | Información de donativos |
| `/rules` | Reglamento de la comunidad |
| `/info` `/id` `/mi_info` | Información de usuarios y chats |
| `/status` | Estado del bot (simplificado para usuarios) |

### Admins y moderadores
| Comando | Descripción |
|---|---|
| `/add <ids...>` | Crear elementos desde rangos de mensajes |
| `/del <id>` | Eliminar un elemento con confirmación |
| `/buscar <texto>` | Buscar con ID visible y paginación |
| `/publicar <id>` | Publicar un elemento en el canal |
| `/recomendar <id>` | Destacar un elemento |
| `/quitar_recomendado <id>` | Quitar el destaque |
| `/notify` | Wizard de notificaciones masivas |
| `/add_mod` `/del_mod` `/list_mod` | Gestión de moderadores |
| `/stats_db` `/stats_users` | Estadísticas detalladas |
| `/db_backup` | Exportar toda la BD como ZIP |
| `/db_restore` | Importar un backup ZIP |
| `/status` | Estado avanzado del sistema (CPU, RAM, userbot) |
| `/qr <url>` | Generar código QR |
| `/acortar <url>` | Acortar enlace con Rebrandly |
| `/ps4` `/switch` `/juego` | Buscar en IGDB por plataforma |
| `/busqueda <juego>` | Scraping en sitios de repacks |
| `/ping` | Diagnóstico de recepción de comandos |

### Userbot (en el almacén)
| Comando | Descripción |
|---|---|
| `/index` | Escanear mensajes nuevos y crear elementos automáticamente |

---

## 🔄 Flujo principal de entrega

```
Usuario → /start?start=TOKEN
    ↓
Validar token (32 chars alfanumérico ó 12dígitos_sufijo)
    ↓
Verificar membresía en canales configurados
    ↓ (si no es miembro)
Mostrar botones de unión + botón reintentar
    ↓ (si es miembro)
Registrar solicitud (deduplicada por usuario)
    ↓
copy_message de id_inicio a id_final desde almacen_id → chat privado
    ↓
Notificar al staff en topic de logs
    ↓
Sugerir compartir el canal
```

---

## 🔄 Flujo de indexado

```
Admin → /index (en el grupo almacén)
    ↓
Userbot (Telethon) escanea desde último id_final registrado
    ↓
Detecta bloques: mensaje con foto + "🎲 Géneros:"
    ↓
Calcula peso y número de archivos del bloque
    ↓
Crea elementos en MongoDB con almacen_id del grupo actual
    ↓
Encola tarea en publicacion_pendiente
    ↓
Bot principal recibe botón "✅ Confirmar"
    ↓
Publica en el canal correspondiente según ALMACENES_MAP
```

---

## 📄 Licencia

Uso privado. No redistribuir sin autorización.
