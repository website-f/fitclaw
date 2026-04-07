import asyncio
from pathlib import Path

from telegram import BotCommand, PhotoSize, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.core.config import get_settings
from app.core.database import session_scope
from app.models.uploaded_asset import UploadedAsset
from app.services.command_result import MessageAttachment
from app.services.message_service import MessageService
from app.services.runtime_config_service import RuntimeConfigService
from app.services.upload_service import UploadService

settings = get_settings()

HELP_TEXT = (
    "I am your AI ops bot.\n"
    "\n"
    "Commands:\n"
    "/start - confirm the bot is online\n"
    "/help - show usage tips\n"
    "/agents - list registered agents and their status\n"
    "/screenshot [agent] - capture a screenshot from an agent\n"
    "/codex <agent> | <path> | <prompt> - run a Codex prompt on an agent\n"
    "/models - show the active model and installed Ollama models\n"
    "/usemodel <provider> <model> - switch runtime model, example: /usemodel ollama qwen2.5:3b\n"
    "\n"
    "Device commands:\n"
    "- verify my agent\n"
    "- list agents\n"
    "- take a screenshot from office-pc\n"
    "- show windows on office-pc\n"
    "- show processes on office-pc\n"
    "- open vscode on office-pc in C:\\projects\\repo\n"
    "- run this prompt inside vscode codex on office-pc in C:\\projects\\repo: fix the failing tests\n"
    "\n"
    "Task commands:\n"
    "- start task office-pc: run the nightly sync\n"
    "- check status\n"
    "- check status tsk_xxxxx\n"
    "- continue task tsk_xxxxx add more instructions\n"
    "\n"
    "Uploads:\n"
    "- send a photo with a caption like `describe this image`\n"
    "- send a photo with `make this grayscale`\n"
    "- send a photo with `remove background`\n"
    "- send a document with `summarize this file`\n"
    "- send a document with `rewrite this file to be more concise`\n"
)


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Check that the AI ops bot is online"),
            BotCommand("help", "Show command and task usage"),
            BotCommand("agents", "List registered agents"),
            BotCommand("screenshot", "Capture a screenshot from an agent"),
            BotCommand("codex", "Run a Codex prompt on an agent"),
            BotCommand("models", "Show active and available models"),
            BotCommand("usemodel", "Switch the runtime model"),
        ]
    )


def build_application() -> Application:
    application = Application.builder().token(settings.telegram_bot_token).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("agents", agents_command))
    application.add_handler(CommandHandler("screenshot", screenshot_command))
    application.add_handler(CommandHandler("codex", codex_command))
    application.add_handler(CommandHandler("models", models_command))
    application.add_handler(CommandHandler("usemodel", usemodel_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, media_message))
    return application


def is_authorized(user_id: int) -> bool:
    allowed = settings.telegram_allowed_user_id_set
    return not allowed or user_id in allowed


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    await update.message.reply_text(
        "The AI ops platform is online. Send a normal message to chat, or use task commands like `start task`.",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    await update.message.reply_text(HELP_TEXT)


async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return

    text = await asyncio.to_thread(get_models_text_sync)
    await update.message.reply_text(text)


async def agents_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    result = await asyncio.to_thread(
        process_message_sync,
        str(update.effective_user.id),
        "list agents",
        update.effective_user.username or update.effective_user.full_name,
        f"telegram:{update.effective_user.id}",
    )
    await deliver_processed_message(update, result)


async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.effective_chat:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return

    suffix = " ".join(context.args).strip()
    text = f"take a screenshot from {suffix}" if suffix else "take a screenshot from my current agent"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
    result = await asyncio.to_thread(
        process_message_sync,
        str(update.effective_user.id),
        text,
        update.effective_user.username or update.effective_user.full_name,
        f"telegram:{update.effective_user.id}",
    )
    await deliver_processed_message(update, result)


async def codex_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.effective_chat:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return

    raw = " ".join(context.args).strip()
    if not raw or "|" not in raw:
        await update.message.reply_text(
            "Usage: /codex <agent> | <path> | <prompt>\nExample: /codex office-pc | C:\\projects\\repo | fix the failing tests",
        )
        return

    parts = [item.strip() for item in raw.split("|", 2)]
    if len(parts) != 3 or not parts[0] or not parts[2]:
        await update.message.reply_text(
            "Usage: /codex <agent> | <path> | <prompt>\nExample: /codex office-pc | C:\\projects\\repo | fix the failing tests",
        )
        return

    agent_name, workspace_path, prompt = parts
    normalized_text = f"run this prompt inside vscode codex on {agent_name}"
    if workspace_path:
        normalized_text += f" in {workspace_path}"
    normalized_text += f": {prompt}"

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    result = await asyncio.to_thread(
        process_message_sync,
        str(update.effective_user.id),
        normalized_text,
        update.effective_user.username or update.effective_user.full_name,
        f"telegram:{update.effective_user.id}",
    )
    await deliver_processed_message(update, result)


async def usemodel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /usemodel <provider> <model>. Example: /usemodel ollama qwen2.5:3b")
        return

    provider = context.args[0]
    model = " ".join(context.args[1:])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    result = await asyncio.to_thread(set_model_sync, provider, model)
    await update.message.reply_text(result)


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_chat or not update.message or not update.message.text:
        return

    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    result = await asyncio.to_thread(
        process_message_sync,
        str(user.id),
        update.message.text,
        user.username or user.full_name,
        f"telegram:{user.id}",
    )
    await deliver_processed_message(update, result)


async def media_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_chat or not update.message:
        return

    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return

    attachment_asset_ids = await collect_telegram_attachments(update, context)
    if not attachment_asset_ids:
        await update.message.reply_text("I could not read that attachment.")
        return

    prompt = (update.message.caption or "").strip()
    if not prompt:
        prompt = "Describe this image." if update.message.photo else "Summarize this file."

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    result = await asyncio.to_thread(
        process_message_sync,
        str(user.id),
        prompt,
        user.username or user.full_name,
        f"telegram:{user.id}",
        attachment_asset_ids,
    )
    await deliver_processed_message(update, result)


def process_message_sync(
    user_id: str,
    text: str,
    username: str | None,
    session_id: str,
    attachment_asset_ids: list[str] | None = None,
):
    with session_scope() as db:
        return MessageService.process_user_message(
            db=db,
            user_id=user_id,
            text=text,
            username=username,
            session_id=session_id,
            attachment_asset_ids=attachment_asset_ids,
        )


async def deliver_processed_message(update: Update, result) -> None:
    if not update.message:
        return

    attachments: list[MessageAttachment] = list(getattr(result, "attachments", []) or [])
    if not attachments:
        await update.message.reply_text(result.reply)
        return

    if len(attachments) == 1 and attachments[0].kind == "photo" and len(result.reply) <= 900:
        attachment = attachments[0]
        resolved = attachment.resolve_path()
        if resolved and resolved.exists():
            with resolved.open("rb") as handle:
                await update.message.reply_photo(photo=handle, caption=result.reply)
            return

    await update.message.reply_text(result.reply)

    for attachment in attachments:
        await send_attachment(update, attachment)


async def send_attachment(update: Update, attachment: MessageAttachment) -> None:
    if not update.message:
        return

    resolved = attachment.resolve_path()
    if resolved is None or not resolved.exists():
        await update.message.reply_text(f"Attachment file was not found: {attachment.path}")
        return

    with resolved.open("rb") as handle:
        if attachment.kind == "photo":
            await update.message.reply_photo(photo=handle, caption=attachment.caption)
        else:
            await update.message.reply_document(
                document=handle,
                caption=attachment.caption,
                filename=attachment.filename or Path(resolved).name,
            )


def get_models_text_sync() -> str:
    with session_scope() as db:
        active = RuntimeConfigService.get_active_llm(db)
    installed = RuntimeConfigService.list_ollama_models()
    configured = settings.ollama_model_list

    lines = [
        f"Active model: {active['provider']} / {active['model']}",
        f"Default model: ollama / {settings.ollama_model}",
        "",
        "Configured Ollama models:",
    ]

    if configured:
        lines.extend([f"- {name}" for name in configured])
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Installed Ollama models:")
    if installed:
        lines.extend([f"- {name}" for name in installed])
    else:
        lines.append("- none yet")

    if settings.gemini_enabled:
        lines.extend(["", f"Gemini fallback available: {settings.gemini_model}"])

    return "\n".join(lines)


def set_model_sync(provider: str, model: str) -> str:
    try:
        validated_provider, validated_model = RuntimeConfigService.validate_provider_model(provider, model)
    except ValueError as exc:
        return str(exc)

    if validated_provider == "ollama":
        installed = RuntimeConfigService.list_ollama_models()
        if validated_model not in installed:
            try:
                RuntimeConfigService.pull_ollama_model(validated_model)
            except Exception as exc:
                return f"Failed to pull Ollama model `{validated_model}`: {exc}"

    with session_scope() as db:
        active = RuntimeConfigService.set_active_llm(db, provider=validated_provider, model=validated_model)

    return f"Active model switched to {active['provider']} / {active['model']}"


async def collect_telegram_attachments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    if not update.message or not update.effective_user:
        return []

    uploaded_assets: list[UploadedAsset] = []

    if update.message.photo:
        uploaded = await upload_telegram_photo(update.message.photo[-1], update.effective_user.id, context)
        if uploaded is not None:
            uploaded_assets.append(uploaded)

    if update.message.document:
        uploaded = await upload_telegram_document(update.message.document, update.effective_user.id, context)
        if uploaded is not None:
            uploaded_assets.append(uploaded)

    return [asset.asset_id for asset in uploaded_assets]


async def upload_telegram_photo(photo: PhotoSize, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> UploadedAsset | None:
    telegram_file = await context.bot.get_file(photo.file_id)
    data = bytes(await telegram_file.download_as_bytearray())
    with session_scope() as db:
        return UploadService.create_asset_from_bytes(
            db=db,
            platform_user_id=str(user_id),
            session_id=f"telegram:{user_id}",
            source="telegram_photo",
            original_filename=f"telegram-photo-{photo.file_unique_id}.jpg",
            mime_type="image/jpeg",
            raw_bytes=data,
        )


async def upload_telegram_document(document, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> UploadedAsset | None:
    telegram_file = await context.bot.get_file(document.file_id)
    data = bytes(await telegram_file.download_as_bytearray())
    with session_scope() as db:
        return UploadService.create_asset_from_bytes(
            db=db,
            platform_user_id=str(user_id),
            session_id=f"telegram:{user_id}",
            source="telegram_document",
            original_filename=document.file_name or f"telegram-document-{document.file_unique_id}",
            mime_type=document.mime_type or "application/octet-stream",
            raw_bytes=data,
        )
