"""
Sistema de gestion de solicitudes y reportes con hashtags.
"""

import logging
import os
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

from config import GROUP_ADMIN_ID, GP_ADMINS, TOPIC_SOLICITUDES, TOPIC_ERRORES, BOT_URL, ADMIN_IDS, MOD_IDS, ADMINISTRATION_GROUP
from database.base import get_database
from database.models.schemas import TicketSolicitudSchema
from database.crud.usuario_crud import UsuarioCRUD
from external_apis.game_search import buscar_en_sitios_web

HASHTAGS_SOLICITUDES    = {"#game", "#games", "#juego", "#juegos", "#solicitud", "#pedido", "#ps4", "#switch"}
HASHTAGS_ERRORES        = {"#sos", "#ayuda", "#help", "#bug", "#report", "#error"}
MAX_SOLICITUDES_ACTIVAS = 5
SOLICITUDES_POR_PAGINA  = 8

logger = logging.getLogger(__name__)

ultimo_mensaje_busqueda = {}
mensajes_solicitud      = {}  # Almacena datos para la paginación y el botón de "Crear Solicitud"


async def borrar_mensaje_temporal(bot, chat_id, message_id, delay=30):
    """Espera X segundos y borra el mensaje para mantener limpio el grupo."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


def obtener_nombre_almacen(almacen_id) -> str:
    """Traduce el ID del almacén a su nombre legible"""
    if not almacen_id or almacen_id == 0:
        return "PC"
    aid_str = str(almacen_id)
    if aid_str == str(ADMINISTRATION_GROUP): return "PC"
    if aid_str == str(os.getenv('ALMACEN_PS4', '')): return "PS4"
    if aid_str == str(os.getenv('ALMACEN_SWITCH', '')): return "Switch"
    if aid_str == str(os.getenv('ALMACEN_CANAIMA', '')): return "Canaima"
    if aid_str == str(os.getenv('ALMACEN_AUDIOVISUALES', '')): return "Audiovisuales"
    return "PC"


def extraer_hashtags(texto: str) -> set:
    if not texto: return set()
    return {p.lower() for p in texto.split() if p.startswith("#")}


def extraer_mensaje_sin_hashtags(texto: str, hashtags: set) -> str:
    if not texto or not hashtags: return texto.strip()
    return " ".join(p for p in texto.split() if p.lower() not in hashtags).strip()


def determinar_categoria(hashtags: set) -> str | None:
    if hashtags & HASHTAGS_SOLICITUDES: return "solicitudes"
    if hashtags & HASHTAGS_ERRORES: return "errores"
    return None


def es_staff(user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id in MOD_IDS


def _col_tickets():
    return get_database().tickets_solicitudes


def contar_solicitudes_activas(user_id: int) -> int:
    try: return _col_tickets().count_documents({"user_id": user_id, "estado": "activo"})
    except Exception as e: return 0


def solicitud_duplicada(user_id: int, texto: str) -> bool:
    try:
        return _col_tickets().find_one({
            "user_id": user_id, "estado": "activo",
            "texto": {"$regex": f"^{texto.strip()}$", "$options": "i"}
        }) is not None
    except Exception as e: return False


def guardar_ticket(user_id: int, chat_id: int, message_id: int, categoria: str,
                   texto: str, msg_privado_id: int = None, msg_admin_id: int = None) -> str | None:
    try:
        doc = TicketSolicitudSchema.crear(
            user_id=user_id, chat_id=chat_id, message_id=message_id,
            categoria=categoria, texto=texto,
            msg_privado_id=msg_privado_id, msg_admin_id=msg_admin_id
        )
        resultado = _col_tickets().insert_one(doc)
        UsuarioCRUD.abrir_solicitud(user_id)
        return str(resultado.inserted_id)
    except Exception as e: return None


def eliminar_ticket_bd(user_id: int, chat_id: int, message_id: int) -> dict | None:
    try:
        ticket = _col_tickets().find_one_and_delete({
            "user_id": user_id, "chat_id": chat_id,
            "message_id": message_id, "estado": "activo"
        })
        if ticket: UsuarioCRUD.cerrar_solicitud(user_id)
        return ticket
    except Exception as e: return None


def cerrar_ticket(user_id: int, chat_id: int, message_id: int, estado: str) -> dict | None:
    try:
        ticket = _col_tickets().find_one_and_update(
            {"user_id": user_id, "chat_id": chat_id, "message_id": message_id, "estado": "activo"},
            {"$set": {"estado": estado}}
        )
        if ticket: UsuarioCRUD.cerrar_solicitud(user_id)
        return ticket
    except Exception as e: return None


async def _bloquear_ticket_admin(context, ticket: dict, texto_actualizado: str):
    if not ticket or not ticket.get("msg_admin_id"): return
    try:
        await context.bot.edit_message_text(chat_id=GP_ADMINS, message_id=ticket["msg_admin_id"], text=texto_actualizado, parse_mode=ParseMode.HTML, reply_markup=None, disable_web_page_preview=True)
    except Exception: pass


async def buscar_en_db(palabras: list) -> list:
    """Busca en la base de datos local y devuelve hasta 30 coincidencias para permitir paginación."""
    try:
        db = get_database()
        regex_conditions = [{"nombre": {"$regex": p, "$options": "i"}} for p in palabras]
        query = {"$and": regex_conditions} if len(regex_conditions) > 1 else regex_conditions[0]
        return list(db.elementos.find(query).sort("solicitudes", -1).limit(30))
    except Exception as e: return []


async def eliminar_mensaje_anterior(context, chat_id: int):
    if chat_id in ultimo_mensaje_busqueda:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=ultimo_mensaje_busqueda[chat_id])
        except Exception: pass
        finally: del ultimo_mensaje_busqueda[chat_id]


def _generar_vista_resultados(chat_id: int, message_id: int, pagina: int) -> tuple[str, InlineKeyboardMarkup]:
    """Genera el texto y el teclado paginado de los resultados de la base de datos."""
    data = mensajes_solicitud.get(f"{chat_id}:{message_id}")
    if not data: return None, None
    
    resultados = data["resultados"]
    user_id = data["user_id"]
    
    RES_POR_PAGINA = 5
    total_paginas = max(1, (len(resultados) + RES_POR_PAGINA - 1) // RES_POR_PAGINA)
    
    inicio = pagina * RES_POR_PAGINA
    fin = inicio + RES_POR_PAGINA
    bloque = resultados[inicio:fin]
    
    cuerpo = f"🔎 <b>Resultados encontrados en nuestro catálogo</b>\nHe encontrado <b>{len(resultados)}</b> coincidencias:\n\n"
    if total_paginas > 1:
        cuerpo += f"📑 <b>Página {pagina + 1} de {total_paginas}</b>\n\n"
    
    botones = []
    for idx, elem in enumerate(bloque, inicio + 1):
        nombre = elem.get("nombre", "Sin nombre")
        almacen = obtener_nombre_almacen(elem.get("almacen_id"))
        solicitudes = elem.get("solicitudes", 0)
        token = elem.get("token", "")
        enlace = f"{BOT_URL}?start={token}" if token else BOT_URL
        
        cuerpo += (
            f"<b>{idx}. [{almacen}] {nombre}</b>\n"
            f"📊 Solicitudes registradas: {solicitudes}\n\n"
        )
        botones.append([InlineKeyboardButton(f"[{almacen}] {nombre[:20]}...", url=enlace)])
    
    # Navegación
    nav_row = []
    if pagina > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"pag_sol:{user_id}:{chat_id}:{message_id}:{pagina-1}"))
    if pagina < total_paginas - 1:
        nav_row.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"pag_sol:{user_id}:{chat_id}:{message_id}:{pagina+1}"))
    
    if nav_row:
        botones.append(nav_row)
        
    botones.append([InlineKeyboardButton("📩 No lo encuentro - Crear solicitud 📩", callback_data=f"hacer_solicitud:{user_id}:{chat_id}:{message_id}")])
    
    return cuerpo, InlineKeyboardMarkup(botones)


def _construir_ticket_solicitud(nombre_usuario, user_id, username, grupo_origen, grupo_link, texto, hashtags, resultados_web=""):
    tags = f"\n\n<b>🏷️ Hashtags:</b> {' '.join(sorted(hashtags))}" if hashtags else ""
    ticket = (
        f"<b>🎮 NUEVA SOLICITUD DE USUARIO</b>\n{'=' * 35}\n\n"
        f"<b>👤 Usuario:</b> {nombre_usuario}\n<b>🆔 ID:</b> <code>{user_id}</code>\n"
        f"<b>📍 Grupo:</b> {grupo_origen}\n\n"
        f"<b>📝 Mensaje del usuario:</b>\n<blockquote>{texto}</blockquote>{tags}\n\n"
        f"{'=' * 35}\n"
    )
    if resultados_web:
        ticket += f"🌐 <b>BÚSQUEDA RÁPIDA EN LA WEB:</b>\n{resultados_web}"
    else:
        ticket += f"🌐 <i>Búsqueda web sin resultados inmediatos.</i>"
        
    return ticket


def _construir_ticket_error(nombre_usuario, user_id, username, grupo_origen, grupo_link, texto, hashtags):
    return (
        f"<b>🛠 REPORTE DE ERROR</b>\n{'─' * 35}\n\n"
        f"<b>👤 Usuario:</b> {nombre_usuario}\n<b>🆔 ID:</b> <code>{user_id}</code>\n"
        f"<b>📱 Usuario de Telegram:</b> {username}\n\n<b>📍 Grupo:</b> {grupo_origen}\n"
        f"<b>🔗 Mensaje original:</b>\n<a href='{grupo_link}'>Abrir mensaje</a>\n\n"
        f"<b>📝 Descripción del problema:</b>\n<blockquote>{texto}</blockquote>\n\n"
        f"<b>🏷️ Hashtags detectados:</b>\n{' '.join(sorted(hashtags))}"
    )


def _teclado_admin_solicitud(user_id, chat_id, message_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔵 COMPLETAR", callback_data=f"sol_completada:{user_id}:{chat_id}:{message_id}"), InlineKeyboardButton("🔴 DENEGAR", callback_data=f"sol_rechazada:{user_id}:{chat_id}:{message_id}")],
        [InlineKeyboardButton("🔍 NO ENCONTRADO", callback_data=f"sol_no_encontrado:{user_id}:{chat_id}:{message_id}"), InlineKeyboardButton("🟡 IGNORAR", callback_data=f"sol_ignorar:{user_id}:{chat_id}:{message_id}")]
    ])


def _teclado_admin_error(user_id, chat_id, message_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 RESUELTO", callback_data=f"rep_resuelto:{user_id}:{chat_id}:{message_id}"), InlineKeyboardButton("🟡 EN PROCESO", callback_data=f"rep_proceso:{user_id}:{chat_id}:{message_id}")],
        [InlineKeyboardButton("🔴 NO ES ERROR", callback_data=f"rep_no_error:{user_id}:{chat_id}:{message_id}"), InlineKeyboardButton("🟠 IGNORAR", callback_data=f"rep_ignorar:{user_id}:{chat_id}:{message_id}")]
    ])


async def _enviar_ticket_y_notificar(context, user_id, chat_id, message_id, nombre_usuario, username, grupo_origen, grupo_link, texto, hashtags, categoria, resultados_web=""):
    if categoria == "solicitudes":
        texto_ticket  = _construir_ticket_solicitud(nombre_usuario, user_id, username, grupo_origen, grupo_link, texto, hashtags, resultados_web)
        teclado_admin = _teclado_admin_solicitud(user_id, chat_id, message_id)
        topic_id      = TOPIC_SOLICITUDES
    else:
        texto_ticket  = _construir_ticket_error(nombre_usuario, user_id, username, grupo_origen, grupo_link, texto, hashtags)
        teclado_admin = _teclado_admin_error(user_id, chat_id, message_id)
        topic_id      = TOPIC_ERRORES

    msg_admin = await context.bot.send_message(
        chat_id=GP_ADMINS, message_thread_id=topic_id,
        text=texto_ticket, reply_markup=teclado_admin,
        parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )

    guardar_ticket(user_id=user_id, chat_id=chat_id, message_id=message_id, categoria=categoria, texto=texto, msg_privado_id=None, msg_admin_id=msg_admin.message_id)


def _formatear_ticket_lista(ticket: dict, mostrar_usuario: bool = False) -> str:
    fecha     = ticket.get("fecha_creacion")
    fecha_str = fecha.strftime("%d/%m/%Y") if isinstance(fecha, datetime) else "-"
    estado    = ticket.get("estado", "-")
    texto     = ticket.get("texto", "Sin texto")
    categoria = "juego" if ticket.get("categoria") == "solicitudes" else "reporte"
    recorte   = texto[:50] + ("..." if len(texto) > 50 else "")
    linea     = f"[{estado.upper()}] ({categoria}) <b>{recorte}</b>"
    if mostrar_usuario: linea += f"\n   ID usuario: <code>{ticket.get('user_id', '?')}</code>"
    linea += f"\n   {fecha_str}\n"
    return linea


def _construir_vista_usuario(tickets: list, total_historico: int) -> str:
    activos  = [t for t in tickets if t.get("estado") == "activo"]
    cerrados = [t for t in tickets if t.get("estado") != "activo"]
    texto = f"<b>📦 Tus solicitudes</b>\n{'=' * 30}\nTotal enviadas: <b>{total_historico}</b>  |  Activas: <b>{len(activos)}/{MAX_SOLICITUDES_ACTIVAS}</b>\n\n"
    if activos:
        texto += "<b>En curso:</b>\n"
        for t in activos: texto += _formatear_ticket_lista(t)
        texto += "\n"
    if cerrados:
        texto += "<b>🌐 Historial reciente:</b>\n"
        for t in cerrados[:5]: texto += _formatear_ticket_lista(t)
    if not activos and not cerrados:
        texto += "No tienes solicitudes registradas todavía.\n\n💡 Usa <b>#juego nombre_del_juego</b> en el grupo para hacer una solicitud."
    return texto


def _construir_vista_admin(tickets: list, total: int, filtro: str, pagina: int) -> str:
    texto = f"<b>🧾 Panel de gestión de solicitudes</b>\n{'=' * 30}\nTotal: <b>{total}</b>  |  Filtro: <i>{filtro}</i>  |  Pagina {pagina + 1}\n\n"
    if not tickets: return texto + "No hay solicitudes con este filtro."
    for t in tickets: texto += _formatear_ticket_lista(t, mostrar_usuario=True)
    return texto


def _teclado_filtros_admin(filtro_actual: str, pagina: int, total: int) -> InlineKeyboardMarkup:
    filtros = [("Activas", "activo"), ("Completas", "completado"), ("Rechazadas", "rechazado"), ("Todas", "todas")]
    fila_filtros = []
    for label, valor in filtros:
        marcado = "> " if valor == filtro_actual else ""
        fila_filtros.append(InlineKeyboardButton(f"{marcado}{label}", callback_data=f"admsol_filtro:{valor}:0"))
    total_paginas = max(1, (total + SOLICITUDES_POR_PAGINA - 1) // SOLICITUDES_POR_PAGINA)
    fila_nav = []
    if pagina > 0: fila_nav.append(InlineKeyboardButton("<<", callback_data=f"admsol_filtro:{filtro_actual}:{pagina - 1}"))
    fila_nav.append(InlineKeyboardButton(f"{pagina + 1}/{total_paginas}", callback_data="admsol_noop"))
    if pagina < total_paginas - 1: fila_nav.append(InlineKeyboardButton(">>", callback_data=f"admsol_filtro:{filtro_actual}:{pagina + 1}"))
    return InlineKeyboardMarkup([fila_filtros, fila_nav] if fila_nav else [fila_filtros])


async def cmd_solicitudes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        if es_staff(user_id):
            filtro, pagina = "activo", 0
            q = {} if filtro == "todas" else {"estado": filtro}
            total = _col_tickets().count_documents(q)
            tickets = list(_col_tickets().find(q).sort("fecha_creacion", -1).skip(pagina * SOLICITUDES_POR_PAGINA).limit(SOLICITUDES_POR_PAGINA))
            texto = _construir_vista_admin(tickets, total, filtro, pagina)
            await update.message.reply_text(texto, parse_mode=ParseMode.HTML, reply_markup=_teclado_filtros_admin(filtro, pagina, total))
        else:
            usuario_doc = UsuarioCRUD.obtener_usuario(user_id)
            total_historico = usuario_doc.get("total_solicitudes", 0) if usuario_doc else 0
            tickets = list(_col_tickets().find({"user_id": user_id}).sort("fecha_creacion", -1).limit(10))
            await update.message.reply_text(_construir_vista_usuario(tickets, total_historico), parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error en /solicitudes: {e}", exc_info=True)


async def manejar_filtros_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        if not es_staff(query.from_user.id):
            await query.answer("Solo administradores y moderadores pueden usar este panel.", show_alert=True)
            return
        await query.answer()
        if query.data == "admsol_noop": return
        _, filtro, pagina_str = query.data.split(":")
        pagina = int(pagina_str)
        q = {} if filtro == "todas" else {"estado": filtro}
        total = _col_tickets().count_documents(q)
        tickets = list(_col_tickets().find(q).sort("fecha_creacion", -1).skip(pagina * SOLICITUDES_POR_PAGINA).limit(SOLICITUDES_POR_PAGINA))
        await query.edit_message_text(_construir_vista_admin(tickets, total, filtro, pagina), parse_mode=ParseMode.HTML, reply_markup=_teclado_filtros_admin(filtro, pagina, total))
    except Exception: pass


async def procesar_solicitud(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        mensaje = update.message
        if not mensaje or not mensaje.chat or mensaje.chat.id not in GROUP_ADMIN_ID or not GP_ADMINS: return
        texto = mensaje.text or mensaje.caption or ""
        if not texto: return
        hashtags = extraer_hashtags(texto)
        if not hashtags: return
        categoria = determinar_categoria(hashtags)
        if not categoria: return

        usuario = mensaje.from_user
        user_id = usuario.id
        if es_staff(user_id) or user_id == 777000: return
        
        nombre_usuario = usuario.full_name
        username = f"@{usuario.username}" if usuario.username else "Sin username"
        grupo_origen = mensaje.chat.title or "Grupo"
        grupo_link = f"https://t.me/c/{str(mensaje.chat.id).replace('-100', '')}/{mensaje.message_id}"
        chat_id = mensaje.chat.id
        message_id = mensaje.message_id
        
        texto_limpio = extraer_mensaje_sin_hashtags(texto, hashtags)

        # 🚀 VALIDACIÓN: SI EL CAMPO DE SOLICITUD ESTÁ VACÍO
        if not texto_limpio:
            try:
                await mensaje.delete()
            except Exception:
                pass
            msg_error = await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ <a href='tg://user?id={user_id}'>{nombre_usuario}</a>, <b>tu solicitud está vacía.</b>\nDebes incluir el título del juego junto al hashtag.\n\n💡 <i>Ejemplo: <code>#juego Elden Ring</code></i>",
                parse_mode=ParseMode.HTML
            )
            asyncio.create_task(borrar_mensaje_temporal(context.bot, chat_id, msg_error.message_id, 15))
            return

        if categoria == "solicitudes":
            activas = contar_solicitudes_activas(user_id)
            if activas >= MAX_SOLICITUDES_ACTIVAS:
                msg_limite = await mensaje.reply_text(
                    f"Límite alcanzado. Ya tienes <b>{activas}</b> solicitudes activas.", 
                    reply_to_message_id=message_id, 
                    parse_mode=ParseMode.HTML
                )
                asyncio.create_task(borrar_mensaje_temporal(context.bot, chat_id, msg_limite.message_id, 15))
                return
            if solicitud_duplicada(user_id, texto_limpio):
                msg_dup = await mensaje.reply_text(
                    "⚠️ <b>Solicitud duplicada.</b>\nYa tienes una solicitud activa con ese mismo contenido.", 
                    reply_to_message_id=message_id, 
                    parse_mode=ParseMode.HTML
                )
                asyncio.create_task(borrar_mensaje_temporal(context.bot, chat_id, msg_dup.message_id, 15))
                return

        if categoria == "solicitudes":
            await eliminar_mensaje_anterior(context, chat_id)
            palabras = texto_limpio.split()
            
            # 🔎 BÚSQUEDA DIRECTA E INTEGRADA EN DB LOCAL
            if palabras:
                resultados = await buscar_en_db(palabras)
                if resultados:
                    # Guardamos la data en caso de que use la paginación o presione el botón de Crear Solicitud
                    mensajes_solicitud[f"{chat_id}:{message_id}"] = {
                        "texto": texto_limpio, 
                        "hashtags": hashtags, 
                        "nombre": nombre_usuario, 
                        "username": username,
                        "resultados": resultados,
                        "user_id": user_id
                    }
                    
                    cuerpo, teclado = _generar_vista_resultados(chat_id, message_id, 0)
                    
                    # Se envía respondiendo al mensaje original (y sin nombre del usuario)
                    msg_enviado = await context.bot.send_message(
                        chat_id=chat_id, 
                        text=cuerpo, 
                        reply_to_message_id=message_id, 
                        parse_mode=ParseMode.HTML, 
                        reply_markup=teclado, 
                        disable_web_page_preview=True
                    )
                    ultimo_mensaje_busqueda[chat_id] = msg_enviado.message_id
                    
                    # 🚀 TIEMPO AUMENTADO A 60 SEGUNDOS PARA QUE EL USUARIO PUEDA PAGINAR
                    asyncio.create_task(borrar_mensaje_temporal(context.bot, chat_id, msg_enviado.message_id, 60))
                    return  # DETENEMOS AQUÍ, EL USUARIO DEBE PRESIONAR EL BOTÓN PARA ENVIAR LA SOLICITUD
            
            # SI NO HAY COINCIDENCIAS, SE ENVÍA AUTOMÁTICO
            cuerpo = (
                "🔍 <b>No se encontraron coincidencias previas en nuestra base de datos.</b>\n\n"
                "📨 <b>Tu solicitud ha sido enviada automáticamente al equipo de administración.</b>"
            )
            
            msg_enviado = await context.bot.send_message(
                chat_id=chat_id, 
                text=cuerpo, 
                reply_to_message_id=message_id, 
                parse_mode=ParseMode.HTML, 
                disable_web_page_preview=True
            )
            ultimo_mensaje_busqueda[chat_id] = msg_enviado.message_id
            asyncio.create_task(borrar_mensaje_temporal(context.bot, chat_id, msg_enviado.message_id, 30))

            # Búsqueda web silenciosa para los administradores
            try:
                res_web = await buscar_en_sitios_web(texto_limpio)
                texto_web_admin = "\n".join(res_web[:3]) if res_web else ""
            except Exception:
                texto_web_admin = ""
                
        else:
            # ERRORES O REPORTES (Sin mencionar nombre)
            msg_reporte = await context.bot.send_message(
                chat_id=chat_id,
                text="✅ <b>Reporte enviado correctamente.</b>\nEl equipo técnico revisará el problema.",
                reply_to_message_id=message_id,
                parse_mode=ParseMode.HTML
            )
            asyncio.create_task(borrar_mensaje_temporal(context.bot, chat_id, msg_reporte.message_id, 30))

        # 🚀 ENVÍO AL STAFF
        await _enviar_ticket_y_notificar(
            context=context, user_id=user_id, chat_id=chat_id, message_id=message_id,
            nombre_usuario=nombre_usuario, username=username,
            grupo_origen=grupo_origen, grupo_link=grupo_link,
            texto=texto_limpio, hashtags=hashtags, categoria=categoria,
            resultados_web=texto_web_admin if categoria == "solicitudes" else ""
        )
    except Exception as e:
        logger.error(f"Error procesando solicitud: {e}", exc_info=True)


async def manejar_respuesta_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        quien_pulsa = query.from_user.id
        datos = query.data.split(":")
        accion = datos[0]
        
        # Parseo de datos dependiendo de la acción (pag_sol usa 5 variables, el resto 4)
        if accion == "pag_sol":
            if len(datos) != 5: return
            user_id, chat_id, message_id, pagina = int(datos[1]), int(datos[2]), int(datos[3]), int(datos[4])
        else:
            if len(datos) != 4: return
            user_id, chat_id, message_id = int(datos[1]), int(datos[2]), int(datos[3])

        # Manejo de paginación de solicitudes
        if accion == "pag_sol":
            if quien_pulsa != user_id:
                await query.answer("Esta acción es solo para el usuario dueño de la búsqueda.", show_alert=True)
                return
            await query.answer()
            cuerpo, teclado = _generar_vista_resultados(chat_id, message_id, pagina)
            if cuerpo and teclado:
                try:
                    await query.edit_message_text(text=cuerpo, parse_mode=ParseMode.HTML, reply_markup=teclado, disable_web_page_preview=True)
                except Exception: pass
            else:
                await query.edit_message_text(text="La solicitud ha expirado.", parse_mode=ParseMode.HTML)
            return

        # Manejo del botón "Crear Solicitud" por parte del usuario
        if accion == "hacer_solicitud":
            if quien_pulsa != user_id:
                await query.answer("Esta acción es solo para el usuario dueño de la solicitud.", show_alert=True)
                return
            
            activas = contar_solicitudes_activas(user_id)
            if activas >= MAX_SOLICITUDES_ACTIVAS:
                await query.answer(f"Límite alcanzado ({activas}/{MAX_SOLICITUDES_ACTIVAS}). Espera a que se procese alguna.", show_alert=True)
                return
            
            datos_sol = mensajes_solicitud.pop(f"{chat_id}:{message_id}", None)
            if not datos_sol:
                await query.answer("La solicitud ha expirado o ya fue enviada.", show_alert=True)
                return
                
            if solicitud_duplicada(user_id, datos_sol["texto"]):
                await query.answer("Ya tienes una solicitud activa con ese contenido.", show_alert=True)
                return
                
            await query.answer()
            
            # Fetch rápido de webs para el admin
            try:
                res_web = await buscar_en_sitios_web(datos_sol["texto"])
                texto_web_admin = "\n".join(res_web[:3]) if res_web else ""
            except Exception:
                texto_web_admin = ""
                
            grupo_origen = (await context.bot.get_chat(chat_id)).title if await context.bot.get_chat(chat_id) else "Grupo"
            grupo_link = f"https://t.me/c/{str(chat_id).replace('-100', '')}/{message_id}"
            
            await _enviar_ticket_y_notificar(
                context=context, user_id=user_id, chat_id=chat_id, message_id=message_id,
                nombre_usuario=datos_sol["nombre"], username=datos_sol["username"],
                grupo_origen=grupo_origen, grupo_link=grupo_link,
                texto=datos_sol["texto"], hashtags=datos_sol["hashtags"], categoria="solicitudes",
                resultados_web=texto_web_admin
            )
            
            await query.edit_message_text(
                text="📨 <b>Tu solicitud ha sido enviada automáticamente al equipo de administración.</b>", 
                parse_mode=ParseMode.HTML
            )
            return

        # Validación de staff para las respuestas de resolución
        if (accion.startswith("sol_") or accion.startswith("rep_")) and not es_staff(quien_pulsa):
            await query.answer("Solo administradores y moderadores pueden gestionar solicitudes.", show_alert=True)
            return

        await query.answer()

        admin_name = query.from_user.full_name
        
        try:
            user_chat = await context.bot.get_chat(user_id)
            nombre_solicitante = user_chat.first_name
        except Exception:
            nombre_solicitante = "Usuario"

        usuario_mencion = f"<a href='tg://user?id={user_id}'>{nombre_solicitante}</a>"

        mensaje_grupo = None
        botones_grupo, estado_ticket, ticket = None, "", None

        if accion == "sol_completada":
            ticket = cerrar_ticket(user_id, chat_id, message_id, "completado")
            texto_pedido = ticket.get("texto", "tu pedido") if ticket else "tu pedido"
            
            mensaje_grupo = f"✅ {usuario_mencion}, <b>¡Solicitud Completada!</b>\nTu pedido ya fue publicado. Revisa el canal correspondiente.\n\n👨‍💻 <i>Atendido por: {admin_name}</i>"
            botones_grupo = InlineKeyboardMarkup([[InlineKeyboardButton("Ver canal", url="https://t.me/Refugio_Gamer")]])
            estado_ticket = "✅ SOLICITUD COMPLETADA\n"
        
        elif accion == "sol_rechazada":
            ticket = cerrar_ticket(user_id, chat_id, message_id, "rechazado")
            texto_pedido = ticket.get("texto", "tu pedido") if ticket else "tu pedido"
            
            mensaje_grupo = f"🚫 {usuario_mencion}, <b>Solicitud Rechazada</b>\nEl contenido (<i>{texto_pedido}</i>) no cumple las normas o no tiene crack disponible.\n\n👨‍💻 <i>Atendido por: {admin_name}</i>"
            botones_grupo = InlineKeyboardMarkup([[InlineKeyboardButton("Refugio Gamer", url="https://t.me/Refugio_Gamer"), InlineKeyboardButton("Rednite", url="https://t.me/Rednite_bot")]])
            estado_ticket = "❌ SOLICITUD RECHAZADA\n"
        
        elif accion == "sol_no_encontrado":
            ticket = eliminar_ticket_bd(user_id, chat_id, message_id)
            texto_pedido = ticket.get("texto", "tu pedido") if ticket else "tu pedido"
            
            mensaje_grupo = f"🔍 {usuario_mencion}, <b>Juego No Encontrado</b>\nEl juego (<i>{texto_pedido}</i>) no fue encontrado. Intenta con otro título más adelante.\n\n👨‍💻 <i>Atendido por: {admin_name}</i>"
            botones_grupo = InlineKeyboardMarkup([[InlineKeyboardButton("Refugio Gamer", url="https://t.me/Refugio_Gamer"), InlineKeyboardButton("Rednite", url="https://t.me/Rednite_bot")]])
            estado_ticket = "🔍 JUEGO NO ENCONTRADO\n"
        
        elif accion == "sol_ignorar":
            estado_ticket, ticket = "🗑️ SOLICITUD IGNORADA\n", cerrar_ticket(user_id, chat_id, message_id, "ignorado")
        
        elif accion == "rep_resuelto":
            ticket = cerrar_ticket(user_id, chat_id, message_id, "completado")
            mensaje_grupo = f"✅ {usuario_mencion}, <b>Reporte Resuelto</b>\nTu reporte fue atendido y el problema se resolvió. ¡Gracias!\n\n👨‍💻 <i>Atendido por: {admin_name}</i>"
            estado_ticket = "✅ REPORTE RESUELTO\n"
        
        elif accion == "rep_proceso":
            mensaje_grupo = f"🔄 {usuario_mencion}, <b>Reporte en Proceso</b>\nTu reporte está siendo atendido. Te notificaremos pronto.\n\n👨‍💻 <i>Atendido por: {admin_name}</i>"
            estado_ticket = "🔄 REPORTE EN PROCESO\n"
        
        elif accion == "rep_no_error":
            ticket = cerrar_ticket(user_id, chat_id, message_id, "rechazado")
            mensaje_grupo = f"ℹ️ {usuario_mencion}, <b>Reporte No Procesado</b>\nTras revisión, tu reporte no se considera un error relevante.\n\n👨‍💻 <i>Atendido por: {admin_name}</i>"
            estado_ticket = "❌ NO ES UN ERROR\n"
        
        elif accion == "rep_ignorar":
            estado_ticket, ticket = "🗑️ REPORTE IGNORADO\n", cerrar_ticket(user_id, chat_id, message_id, "ignorado")

        # Se envían mensajes permanentes al grupo respondiendo al usuario
        if mensaje_grupo:
            try: 
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=mensaje_grupo, 
                    reply_to_message_id=message_id, # RESPONDE AL MENSAJE ORIGINAL
                    parse_mode=ParseMode.HTML, 
                    reply_markup=botones_grupo
                )
            except Exception: pass

        texto_bloqueado = f"{query.message.text}\n\n{'─' * 35}\n{estado_ticket}Atendido por: {admin_name}"
        if ticket and ticket.get("msg_admin_id"): 
            await _bloquear_ticket_admin(context, ticket, texto_bloqueado)
        else:
            try: await query.edit_message_text(text=texto_bloqueado, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Exception: pass

    except Exception: pass


def register_hashtag_forwarder(application: Application) -> None:
    application.add_handler(MessageHandler(filters.Chat(GROUP_ADMIN_ID) & (filters.TEXT | filters.CAPTION), procesar_solicitud))
    application.add_handler(CommandHandler("solicitudes", cmd_solicitudes))
    application.add_handler(CallbackQueryHandler(manejar_respuesta_admin, pattern="^(sol_|rep_|hacer_solicitud|pag_sol)"))
    application.add_handler(CallbackQueryHandler(manejar_filtros_admin, pattern="^admsol_"))