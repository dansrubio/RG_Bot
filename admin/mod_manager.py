"""
Handler para gestionar moderadores desde Telegram.
Permite añadir, eliminar y listar MOD_IDS en el .env en caliente,
sin necesidad de reiniciar el bot. Solo accesible para ADMIN_IDS.
"""

import os
import re
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import config  # Se usa el módulo directamente para modificar MOD_IDS en memoria


# Raíz del proyecto (sube un nivel desde admin/ hasta llegar al .env)
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _leer_env() -> str:
    """Lee el contenido actual del .env"""
    return ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""


def _guardar_env(contenido: str) -> None:
    """Sobreescribe el .env con el nuevo contenido"""
    ENV_PATH.write_text(contenido, encoding="utf-8")


def _actualizar_mod_ids_en_env(nuevos_ids: list[int]) -> None:
    """Reemplaza la línea MOD_IDS en el .env con la nueva lista"""
    contenido = _leer_env()
    valor = ",".join(str(i) for i in nuevos_ids)
    nueva_linea = f"MOD_IDS={valor}"

    if re.search(r"^MOD_IDS=.*", contenido, re.MULTILINE):  # Reemplazar línea existente
        contenido = re.sub(r"^MOD_IDS=.*", nueva_linea, contenido, flags=re.MULTILINE)
    else:  # Si no existe la línea, agregarla al final
        contenido += f"\n{nueva_linea}\n"

    _guardar_env(contenido)


def _sincronizar_memoria(nuevos_ids: list[int]) -> None:
    """Actualiza MOD_IDS en el módulo config sin reiniciar el bot"""
    config.MOD_IDS.clear()
    config.MOD_IDS.extend(nuevos_ids)


def _obtener_mods() -> list[int]:
    """Devuelve la lista actual de MOD_IDS desde memoria"""
    return list(config.MOD_IDS)


# ── Validación de acceso ──────────────────────────────────────────────────────

def _solo_admins(func):
    """Decorador: rechaza el comando si el usuario no es admin"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not config.is_admin(user_id):
            await update.message.reply_text("⛔ Solo los administradores pueden usar este comando.")
            return
        return await func(update, context)
    return wrapper


# ── Comandos ─────────────────────────────────────────────────────────────────

@_solo_admins
async def cmd_add_mod(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/add_mod <user_id> — Añade un moderador"""
    if not context.args:
        await update.message.reply_text("ℹ️ Uso: /add_mod <user_id>")
        return

    if not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("❌ El ID debe ser un número entero.")
        return

    nuevo_id = int(context.args[0])
    mods = _obtener_mods()

    if nuevo_id in mods:
        await update.message.reply_text(f"⚠️ El ID `{nuevo_id}` ya es moderador.", parse_mode="Markdown")
        return

    mods.append(nuevo_id)
    _sincronizar_memoria(mods)
    _actualizar_mod_ids_en_env(mods)

    logging.info(f"[mod_manager] Admin {update.effective_user.id} añadió moderador {nuevo_id}")
    await update.message.reply_text(f"✅ `{nuevo_id}` añadido como moderador.", parse_mode="Markdown")


@_solo_admins
async def cmd_del_mod(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/del_mod <user_id> — Elimina un moderador"""
    if not context.args:
        await update.message.reply_text("ℹ️ Uso: /del_mod <user_id>")
        return

    if not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("❌ El ID debe ser un número entero.")
        return

    id_a_eliminar = int(context.args[0])
    mods = _obtener_mods()

    if id_a_eliminar not in mods:
        await update.message.reply_text(f"⚠️ El ID `{id_a_eliminar}` no está en la lista de moderadores.", parse_mode="Markdown")
        return

    mods.remove(id_a_eliminar)
    _sincronizar_memoria(mods)
    _actualizar_mod_ids_en_env(mods)

    logging.info(f"[mod_manager] Admin {update.effective_user.id} eliminó moderador {id_a_eliminar}")
    await update.message.reply_text(f"🗑️ `{id_a_eliminar}` eliminado de moderadores.", parse_mode="Markdown")


@_solo_admins
async def cmd_list_mod(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/list_mod — Lista todos los moderadores activos"""
    mods = _obtener_mods()

    if not mods:
        await update.message.reply_text("📋 No hay moderadores registrados.")
        return

    lineas = "\n".join(f"• `{mod_id}`" for mod_id in mods)
    await update.message.reply_text(
        f"📋 *Moderadores activos ({len(mods)}):*\n{lineas}",
        parse_mode="Markdown"
    )


# ── Registro en la app ────────────────────────────────────────────────────────

def register_mod_manager_handlers(app: Application) -> None:
    """Registra los comandos de gestión de moderadores"""
    app.add_handler(CommandHandler("add_mod", cmd_add_mod))
    app.add_handler(CommandHandler("del_mod", cmd_del_mod))
    app.add_handler(CommandHandler("list_mod", cmd_list_mod))