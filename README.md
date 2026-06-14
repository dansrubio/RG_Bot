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

## 🏗️ Estructura del proyecto

```
rednite-bot/
│
├── main.py                     # Punto de entrada, registro de handlers
├── config.py                   # Variables de entorno y funciones de permisos
├── requirements.txt
│
├── database/
│   ├── base.py                 # Conexión pymongo + motor (async)
│   ├── manager.py              # Setup y cierre de la BD
│   ├── crud/
│   │   ├── elemento_crud.py    # CRUD completo de elementos
│   │   └── usuario_crud.py     # CRUD de usuarios
│   └── models/
│       └── schemas.py          # Esquemas de documentos MongoDB
│
├── admin/                      # Comandos exclusivos de admins/mods
│   ├── elemento_handler.py     # /add, /del, /info_elementos, /stats_elementos
│   ├── busqueda_elemento_handler.py  # /buscar con paginación
│   ├── index_publisher_handler.py   # Publicación post-indexado
│   ├── top_elementos_handler.py     # /top_all, /top_pc, /top_ps4...
│   ├── juego_aleatorio_handler.py   # /juego_aleatorio
│   ├── recomendaciones_handler.py   # /recomendar, /recomendados
│   ├── notify_handler.py            # /notify — notificaciones masivas
│   ├── mod_manager.py               # /add_mod, /del_mod, /list_mod
│   ├── stats_handler.py             # /stats_db, /stats_users
│   ├── db_backup.py                 # /db_backup
│   ├── db_restore.py                # /db_restore
│   └── status.py                    # /status
│
├── automation/                 # Handlers automáticos del flujo normal
│   ├── start_handler.py        # /start con entrega de archivos y verificación
│   ├── catalogo_handler.py     # /catalogo con navegación A-Z y paginación
│   ├── hashtag_forwarder.py    # Sistema de tickets via hashtags (#juego, #sos...)
│   ├── verification_handler.py # Silencio y verificación de nuevos miembros
│   ├── message_tracker.py      # Registro automático de usuarios en MongoDB
│   ├── cleaner.py              # Limpieza de mensajes de servicio de Telegram
│   ├── autoliker_handler.py    # Reacciones automáticas (bot principal)
│   ├── autoliker_userbot.py    # Reacciones automáticas (userbot Telethon)
│   ├── pokedex_handler.py      # /pokemon, /pkm_move, /pkm_item, /pkm_type
│   └── yugioh_handler.py       # /carta, /arquetipo, /sets, /precio
│
├── external_apis/
│   ├── steam_api.py            # /game — búsqueda en Steam con Telegraph
│   ├── igdb_api.py             # /ps4, /switch, /juego — búsqueda en IGDB
│   ├── game_search.py          # /busqueda — scraping de PiviGames, FitGirl, GameDrive
│   ├── qr_generator.py         # /qr
│   ├── rebrandly.py            # /acortar
│   ├── pokeapi.py              # Cliente PokeAPI (async con httpx)
│   ├── yugioh.py               # Cliente YGOPRODeck
│   ├── free_games/
│   │   ├── handler.py          # /juegosgratis, job periódico
│   │   ├── sources.py          # Agrega epic.py + gog.py + steam.py
│   │   ├── epic.py             # Epic Games Store API
│   │   ├── gog.py              # GamerPower API (GOG)
│   │   ├── steam.py            # GamerPower API (Steam)
│   │   └── sent_games_manager.py  # Deduplicación en MongoDB
│   └── services/
│       ├── igdb_telegraph_service.py   # Páginas Telegraph para fichas IGDB
│       └── steam_telegraph_service.py  # Páginas Telegraph para fichas Steam
│
├── helpers/
│   ├── auto_publisher.py       # Lógica de publicación en canales
│   ├── auto_response.py        # /donate, /rules
│   ├── temp_storage.py         # Cache TTL para callback_data largo
│   ├── text_utils.py           # Limpieza de texto para nombres y botones
│   ├── verification_system.py  # Lógica de membresía en canales
│   ├── notifications.py        # Notificaciones privadas de sanciones
│   ├── daily_summary.py        # Resumen diario automático
│   ├── random_handler.py       # /random — generador de claves
│   ├── secure_keys.py          # Generador de contraseñas/PINs/tokens
│   ├── time_parser.py          # Parser de duraciones (7d6h30m → segundos)
│   ├── telegram_filters.py     # Filtros para IDs del sistema de Telegram
│   ├── wow_token_handler.py    # /wow_token
│   ├── wow_token_service.py    # Cliente de wowtoken.app
│   └── debug_handlers.py       # /ping para diagnóstico
│
├── info/
│   ├── userinfo.py             # /info, /id, /mi_info
│   ├── user_command.py         # /user @username o ID
│   ├── channelinfo.py          # Detección de /channel en canales
│   └── watchdog.py             # Alertas de CPU/RAM/disco a admins
│
└── userbot_indexer.py          # Userbot Telethon: /index + autoliker
```

---

## ⚙️ Configuración

### 1. Clonar e instalar dependencias

```bash
git clone https://github.com/tu-usuario/rednite-bot.git
cd rednite-bot
pip install -r requirements.txt
```

### 2. Crear `config.env`

```env
# === BOT ===
BOT_TOKEN=123456789:ABCdef...
BOT_URL=https://t.me/tu_bot

# === ADMINS Y MODS ===
ADMIN_IDS=111111111,222222222
MOD_IDS=333333333

# === GRUPOS Y CANALES ===
GROUP_ADMIN_ID=-100111111111,-100222222222
GP_ADMINS=-100333333333
ADMINISTRATION_GROUP=-100444444444
CANAL_ELEMENTOS=-100555555555

# === ALMACENES ADICIONALES (opcional) ===
ALMACEN_PS4=-100666666666
CANAL_PS4=-100777777777
ALMACEN_SWITCH=-100888888888
CANAL_SWITCH=-100999999999
ALMACEN_CANAIMA=-100000000001
CANAL_CANAIMA=-100000000002
ALMACEN_AUDIOVISUALES=-100000000003
CANAL_AUDIOVISUALES=-100000000004

# === TOPICS ===
TOPIC_SOLICITUDES=12
TOPIC_ERRORES=14
TOPIC_LOG_SOLICITUDES=6218

# === MONGODB ===
MONGODB_URI=mongodb+srv://usuario:password@cluster.mongodb.net/
MONGODB_DATABASE=rednite_bot

# === VERIFICACIÓN DE CANALES ===
BOT_VERIFICATION_CHANNELS=-100111111111,-100222222222

# === USERBOT (Telethon) ===
USERBOT_API_ID=12345678
USERBOT_API_HASH=abcdef1234567890abcdef1234567890
USERBOT_SESSION=rg_manager

# === APIS EXTERNAS ===
IGDB_CLIENT_ID=tu_client_id
IGDB_CLIENT_SECRET=tu_client_secret
STEAM_API_KEY=tu_steam_key
RAWG_API_KEY=tu_rawg_key
REBRANDLY_API_KEY=tu_rebrandly_key

# === JUEGOS GRATIS ===
FREE_GAMES_GRUPOS=-100111111111
FREE_GAMES_CANALES=-100222222222
FREE_GAMES_INTERVALO_HORAS=4

# === DOCUMENTACIÓN ===
BOT_REGLAMENTO_URL=https://t.me/...
BOT_PRIVACIDAD_URL=https://t.me/...
```

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

## 🗄️ Esquema MongoDB

### Colección `elementos`
```json
{
  "_id": ObjectId,
  "nombre": "string",
  "token": "string (único, generado atómicamente)",
  "id_inicio": 1000,
  "id_final": 1015,
  "almacen_id": -100444444444,
  "creador_id": 111111111,
  "solicitudes": 42,
  "peso_bytes": 7340032,
  "num_archivos": 3,
  "informacion_completa": "texto del post original",
  "recomendado": false,
  "fecha_creacion": ISODate
}
```

### Colección `usuarios`
```json
{
  "_id": 111111111,
  "username": "nombre_usuario",
  "name": "Nombre Completo",
  "solicitudes": 7
}
```

### Colección `elemento_solicitudes`
```json
{
  "elemento_id": ObjectId,
  "user_id": 111111111,
  "timestamp": ISODate
}
```

### Colección `tickets_solicitudes`
```json
{
  "user_id": 111111111,
  "chat_id": -100111111111,
  "message_id": 12345,
  "categoria": "solicitudes",
  "texto": "Elden Ring",
  "estado": "activo",
  "msg_admin_id": 99,
  "fecha_creacion": ISODate
}
```

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

## 🧰 Tecnologías

- **Python 3.10+**
- **python-telegram-bot 20+** (async, job-queue)
- **Telethon** — userbot indexador
- **pymongo + motor** — MongoDB sync y async
- **aiohttp / httpx** — peticiones HTTP async
- **cachetools** — cache TTL en memoria
- **BeautifulSoup4** — scraping de sitios de repacks
- **telegraph** — publicación de fichas técnicas
- **psutil** — monitoreo del sistema

---

## 📄 Licencia

Uso privado. No redistribuir sin autorización.
