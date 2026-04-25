import asyncio
from pathlib import Path

import httpx
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, PhotoSize, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.core.config import get_settings
from app.core.database import session_scope
from app.models.uploaded_asset import UploadedAsset
from app.services.command_result import MessageAttachment
from app.services.message_service import MessageService
from app.services.runtime_config_service import RuntimeConfigService
from app.services.upload_service import UploadService
from app.services.vps_stats_service import ProjectsClient, RouterClient, UsageService, VpsStatsService, VpsStatsUnavailable

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
    "/models - show the active model with daily, coding, vision, and cloud options\n"
    "/usemodel <provider> <model> - switch runtime model, example: /usemodel ollama qwen2.5:3b\n"
    "  Quick picks: qwen3-coder:30b, qwen2.5-coder:7b, gemma3:4b, deepseek-r1:1.5b, kimi-k2.5:cloud\n"
    "\n"
    "Device commands:\n"
    "- verify my agent\n"
    "- list agents\n"
    "- take a screenshot from office-pc\n"
    "- check storage on office-pc and list top 10 biggest folders and files\n"
    "- ask office-pc to crawl https://example.com and summarize it\n"
    "- ask office-pc to open https://shopee.com.my/product/... tomorrow at 11:59pm\n"
    "- show windows on office-pc\n"
    "- show processes on office-pc\n"
    "- open vscode on office-pc in C:\\projects\\repo\n"
    "- run this prompt inside vscode codex on office-pc in C:\\projects\\repo: fix the failing tests\n"
    "- high-risk browser automations like checkout or purchase will ask for confirmation first\n"
    "\n"
    "Task commands:\n"
    "- start task office-pc: run the nightly sync\n"
    "- check status\n"
    "- check status tsk_xxxxx\n"
    "- continue task tsk_xxxxx add more instructions\n"
    "\n"
    "Uploads:\n"
    "- send a photo by itself and I will ask what you want done with it\n"
    "- send a photo with `what is this`\n"
    "- send a photo with `make this grayscale`\n"
    "- send a photo with `remove background`\n"
    "- send a photo with `find Shopee links for this`\n"
    "- send a document with `summarize this file`\n"
    "- send a document with `rewrite this file to be more concise`\n"
    "- upload PDFs, DOCX, XLSX/XLS, CSV/TSV, code files, or text files and ask for a summary\n"
    "\n"
    "Links:\n"
    "- paste one or more URLs and ask `summarize this` or `what does this page say?`\n"
    "- the bot will crawl the provided links, extract readable content, and summarize what it found\n"
    "- if you want a specific device agent to do the crawl or open the page later, name that agent in the prompt\n"
    "\n"
    "Weather:\n"
    "- `weather in Shah Alam tomorrow`\n"
    "- `will it rain in Kuala Lumpur today?`\n"
    "- `show active weather warnings in Penang`\n"
    "\n"
    "Transit:\n"
    "- `how do I go from Taman Bahagia to KLCC by LRT?`\n"
    "- `route from Pasar Seni to Bukit Bintang via MRT`\n"
    "- `show live buses in KL`\n"
    "- for a live map and provider selector, open `/transit-live` in the web UI\n"
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
            BotCommand("stats", "Show VPS CPU / RAM / disk / uptime"),
            BotCommand("processes", "Top processes by CPU (add `mem` for memory)"),
            BotCommand("disks", "List mounted filesystems and usage"),
            BotCommand("usage", "Token + cost usage (today | week | month)"),
            BotCommand("claude", "Run a Claude Code prompt on an agent PC"),
            BotCommand("vscode", "List open VS Code windows on the agent"),
            BotCommand("sessions", "List recent Claude Code sessions on the agent"),
            BotCommand("projects", "List registered code projects"),
            BotCommand("fix", "Dispatch a fix to a project — /fix <slug> | <issue>"),
            BotCommand("push", "Show branch selector to push a project"),
            BotCommand("deploy", "Trigger deploy_command for a project"),
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
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("processes", processes_command))
    application.add_handler(CommandHandler("disks", disks_command))
    application.add_handler(CommandHandler("usage", usage_command))
    application.add_handler(CommandHandler("claude", claude_command))
    application.add_handler(CommandHandler("vscode", vscode_command))
    application.add_handler(CommandHandler("sessions", sessions_command))
    application.add_handler(CommandHandler("projects", projects_command))
    application.add_handler(CommandHandler("fix", fix_command))
    application.add_handler(CommandHandler("push", push_command))
    application.add_handler(CommandHandler("deploy", deploy_command))
    application.add_handler(CallbackQueryHandler(approval_callback, pattern=r"^app_(approve|deny):"))
    application.add_handler(CallbackQueryHandler(branch_push_callback, pattern=r"^push_branch:"))
    application.add_handler(CallbackQueryHandler(deploy_callback, pattern=r"^deploy:"))
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


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        stats = await asyncio.to_thread(VpsStatsService.fetch)
    except VpsStatsUnavailable as exc:
        await update.message.reply_text(f"vps_stats is unreachable: {exc}")
        return
    await update.message.reply_text(VpsStatsService.format_for_telegram(stats), parse_mode=None)


async def processes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    args = [arg.lower() for arg in (context.args or [])]
    by = "mem" if "mem" in args or "memory" in args else "cpu"
    top = 10
    for arg in args:
        if arg.isdigit():
            top = max(1, min(50, int(arg)))
            break
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        rows = await asyncio.to_thread(VpsStatsService.fetch_processes, top, by)
    except VpsStatsUnavailable as exc:
        await update.message.reply_text(f"vps_stats is unreachable: {exc}")
        return
    text = VpsStatsService.format_processes_for_telegram(rows, by)
    await update.message.reply_text(f"```\n{text}\n```", parse_mode="Markdown")


async def disks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        rows = await asyncio.to_thread(VpsStatsService.fetch_disks)
    except VpsStatsUnavailable as exc:
        await update.message.reply_text(f"vps_stats is unreachable: {exc}")
        return
    text = VpsStatsService.format_disks_for_telegram(rows)
    await update.message.reply_text(f"```\n{text}\n```", parse_mode="Markdown")


async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Approve/Deny button taps from an approval Telegram message."""
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return
    if not is_authorized(query.from_user.id):
        await query.answer("Not authorized.", show_alert=True)
        return

    try:
        action, approval_id = query.data.split(":", 1)
    except ValueError:
        await query.answer("Malformed callback.", show_alert=True)
        return

    approved = action == "app_approve"
    decided_by = query.from_user.username or str(query.from_user.id)

    api_url = settings.api_internal_url.rstrip("/")

    def _decide_sync() -> dict | None:
        try:
            response = httpx.post(
                f"{api_url}/api/v1/approvals/{approval_id}/decide",
                json={"approved": approved, "decided_by": decided_by},
                timeout=5.0,
            )
            if response.status_code >= 400:
                return None
            return response.json()
        except httpx.HTTPError:
            return None

    result = await asyncio.to_thread(_decide_sync)
    if result is None:
        await query.answer("Failed to record decision.", show_alert=True)
        return
    await query.answer("Approved." if approved else "Denied.")


async def projects_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    try:
        rows = await asyncio.to_thread(ProjectsClient.list_projects)
    except VpsStatsUnavailable as exc:
        await update.message.reply_text(f"Projects API unreachable: {exc}")
        return
    if not rows:
        await update.message.reply_text(
            "No projects registered yet.\n"
            "Add one with:\n"
            "  curl -X PUT http://api/api/v1/projects/<slug>?user_id=fitclaw \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"slug\":\"...\",\"name\":\"...\",\"keywords\":[\"...\"], "
            "\"agent_name\":\"office-pc\",\"local_path\":\"C:\\\\projects\\\\...\","
            " \"vps_path\":\"/home/admin/...\",\"deploy_command\":\"docker compose up -d\","
            " \"branches\":[\"main\",\"dev\"]}'"
        )
        return
    lines = [f"Registered projects ({len(rows)}):"]
    for row in rows:
        agent = row.get("agent_name") or "-"
        path = row.get("local_path") or "-"
        lines.append(f"  • {row['slug']:<14} ({agent})  {path}")
    await update.message.reply_text("```\n" + "\n".join(lines) + "\n```", parse_mode="Markdown")


async def fix_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch a fix request to a registered project's PC agent.

    Syntax: /fix <slug> | <issue text>
    """
    if not update.effective_user or not update.message or not update.effective_chat:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return

    raw = " ".join(context.args).strip()
    if not raw or "|" not in raw:
        await update.message.reply_text(
            "Usage: /fix <slug> | <issue text>\n"
            "Example: /fix fitclaw | the /usage button doesn't respond on iOS"
        )
        return
    slug_raw, issue = [p.strip() for p in raw.split("|", 1)]
    slug = slug_raw.lower()
    try:
        project = await asyncio.to_thread(ProjectsClient.get, slug)
    except VpsStatsUnavailable as exc:
        await update.message.reply_text(f"Projects API unreachable: {exc}")
        return
    if project is None:
        await update.message.reply_text(
            f"No project registered with slug `{slug}`. Run /projects to see registered ones."
        )
        return
    if not project.get("agent_name") or not project.get("local_path"):
        await update.message.reply_text(
            f"Project `{slug}` is missing `agent_name` or `local_path`. "
            "Set them before dispatching fixes."
        )
        return

    agent_name = project["agent_name"]
    local_path = project["local_path"]
    branch = project.get("default_branch") or "main"
    normalized_text = (
        f"run this prompt inside claude code on {agent_name} in {local_path}: "
        f"You are working on project '{project['name']}' ({slug}). "
        f"Pull latest from branch '{branch}' first, then fix this reported issue: {issue}"
    )
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    result = await asyncio.to_thread(
        process_message_sync,
        str(update.effective_user.id),
        normalized_text,
        update.effective_user.username or update.effective_user.full_name,
        f"telegram:{update.effective_user.id}",
    )
    await deliver_processed_message(update, result)
    # Hint: tell user how to push when done
    await update.message.reply_text(
        f"When the agent finishes, run `/push {slug}` to choose a branch and push the changes."
    )


async def push_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show inline branch keyboard for pushing a project."""
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /push <slug>")
        return
    slug = context.args[0].lower()
    try:
        project = await asyncio.to_thread(ProjectsClient.get, slug)
    except VpsStatsUnavailable as exc:
        await update.message.reply_text(f"Projects API unreachable: {exc}")
        return
    if project is None:
        await update.message.reply_text(f"No project `{slug}`.")
        return
    branches = project.get("branches") or [project.get("default_branch") or "main"]
    keyboard = [
        [InlineKeyboardButton(f"⬆️ Push → {b}", callback_data=f"push_branch:{slug}:{b}")]
        for b in branches[:8]
    ]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"push_branch:{slug}:_cancel")])
    await update.message.reply_text(
        f"Choose target branch for `{slug}`:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def branch_push_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a branch-selection tap from the /push keyboard."""
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return
    if not is_authorized(query.from_user.id):
        await query.answer("Not authorized.", show_alert=True)
        return
    try:
        _, slug, branch = query.data.split(":", 2)
    except ValueError:
        await query.answer("Malformed callback.", show_alert=True)
        return
    if branch == "_cancel":
        await query.answer("Cancelled.")
        await query.edit_message_text(f"Push for `{slug}` cancelled.", parse_mode="Markdown")
        return

    try:
        project = await asyncio.to_thread(ProjectsClient.get, slug)
    except VpsStatsUnavailable as exc:
        await query.answer(f"unreachable: {exc}", show_alert=True)
        return
    if project is None or not project.get("agent_name") or not project.get("local_path"):
        await query.answer(f"project '{slug}' missing agent/path", show_alert=True)
        return

    agent_name = project["agent_name"]
    local_path = project["local_path"]
    push_text = (
        f"run this prompt inside claude code on {agent_name} in {local_path}: "
        f"Stage all current changes, commit with message 'fix dispatched via Telegram', "
        f"then `git push origin {branch}`. "
        f"After push completes, output exactly: PUSH_COMPLETE {slug} {branch}"
    )

    def _dispatch() -> object:
        return process_message_sync(
            str(query.from_user.id),
            push_text,
            query.from_user.username or str(query.from_user.id),
            f"telegram:{query.from_user.id}",
        )

    await query.answer(f"Dispatching push to {branch}…")
    result = await asyncio.to_thread(_dispatch)
    await query.edit_message_text(
        f"⬆️ Push dispatched to agent `{agent_name}` for `{slug}` → `{branch}`.\n"
        f"When the push completes, run `/deploy {slug} {branch}` to redeploy on the VPS.",
        parse_mode="Markdown",
    )


async def deploy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run a project's deploy_command on this VPS."""
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /deploy <slug> [branch]")
        return
    slug = context.args[0].lower()
    branch = context.args[1] if len(context.args) > 1 else None
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Deploy now", callback_data=f"deploy:{slug}:{branch or '-'}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"deploy:{slug}:_cancel"),
    ]])
    branch_text = f" (branch: `{branch}`)" if branch else ""
    await update.message.reply_text(
        f"Confirm deploy for `{slug}`{branch_text}?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def deploy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return
    if not is_authorized(query.from_user.id):
        await query.answer("Not authorized.", show_alert=True)
        return
    try:
        _, slug, branch_arg = query.data.split(":", 2)
    except ValueError:
        await query.answer("Malformed callback.", show_alert=True)
        return
    if branch_arg == "_cancel":
        await query.answer("Cancelled.")
        await query.edit_message_text(f"Deploy for `{slug}` cancelled.", parse_mode="Markdown")
        return
    branch: str | None = None if branch_arg == "-" else branch_arg
    await query.answer("Deploying… (may take a minute)")

    def _run() -> dict:
        try:
            return ProjectsClient.deploy(slug, branch)
        except VpsStatsUnavailable as exc:
            return {"exit_code": -2, "stdout": "", "stderr": str(exc)}

    result = await asyncio.to_thread(_run)
    exit_code = result.get("exit_code", -1)
    icon = "✅" if exit_code == 0 else "❌"
    stderr = (result.get("stderr") or "").strip()
    stdout_tail = (result.get("stdout") or "").strip()[-1500:]
    body = stdout_tail
    if stderr:
        body = (body + "\n\n[stderr]\n" + stderr[-500:]).strip()
    text = (
        f"{icon} Deploy `{slug}`"
        + (f" (branch: `{branch}`)" if branch else "")
        + f" — exit {exit_code}\n\n```\n{body or '(no output)'}\n```"
    )
    await query.edit_message_text(text[:4000], parse_mode="Markdown")


async def vscode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        rows = await asyncio.to_thread(VpsStatsService.fetch_vscode_windows)
    except VpsStatsUnavailable as exc:
        await update.message.reply_text(f"vps_stats unreachable: {exc}")
        return
    text = VpsStatsService.format_vscode_for_telegram(rows)
    await update.message.reply_text(f"```\n{text}\n```", parse_mode="Markdown")


async def sessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        rows = await asyncio.to_thread(VpsStatsService.fetch_claude_sessions)
    except VpsStatsUnavailable as exc:
        await update.message.reply_text(f"vps_stats unreachable: {exc}")
        return
    text = VpsStatsService.format_sessions_for_telegram(rows)
    await update.message.reply_text(f"```\n{text}\n```", parse_mode="Markdown")


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    period = "today"
    if context.args:
        arg = context.args[0].lower()
        if arg in {"today", "week", "month"}:
            period = arg
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        summary = await asyncio.to_thread(UsageService.fetch_summary, period)
    except VpsStatsUnavailable as exc:
        await update.message.reply_text(f"Usage API unreachable: {exc}")
        return
    text = UsageService.format_summary_for_telegram(summary)
    await update.message.reply_text(f"```\n{text}\n```", parse_mode="Markdown")


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


async def claude_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch a Claude Code prompt to a named agent PC.

    Syntax: /claude <agent> | <path> | <prompt>
    Example: /claude office-pc | C:\\projects\\repo | add a unit test for UsageService

    Reuses the existing NL agent-dispatch routing; the agent_daemon on
    the target PC interprets `run this prompt inside claude code on <agent>`
    and runs `claude -p "<prompt>"` in the given path.
    """
    if not update.effective_user or not update.message or not update.effective_chat:
        return
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return

    raw = " ".join(context.args).strip()
    if not raw or "|" not in raw:
        await update.message.reply_text(
            "Usage: /claude <agent> | <path> | <prompt>\n"
            "Example: /claude office-pc | C:\\projects\\repo | add a unit test for UsageService",
        )
        return

    parts = [item.strip() for item in raw.split("|", 2)]
    if len(parts) != 3 or not parts[0] or not parts[2]:
        await update.message.reply_text(
            "Usage: /claude <agent> | <path> | <prompt>\n"
            "Example: /claude office-pc | C:\\projects\\repo | add a unit test for UsageService",
        )
        return

    agent_name, workspace_path, prompt = parts
    normalized_text = f"run this prompt inside claude code on {agent_name}"
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


CONFIDENCE_THRESHOLD = 0.7  # below this → fall through to existing NL chat


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_chat or not update.message or not update.message.text:
        return

    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return

    text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    # 1) Try the smart router first — it handles fix/push/deploy/query/finance/etc.
    routed = await _try_smart_route(update, context, text)
    if routed:
        return

    # 2) Fall through to the existing NL routing layer (general chat,
    #    legacy device-control phrasing, codex routing, etc.)
    result = await asyncio.to_thread(
        process_message_sync,
        str(user.id),
        text,
        user.username or user.full_name,
        f"telegram:{user.id}",
    )
    await deliver_processed_message(update, result)


async def _try_smart_route(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> bool:
    """Classify + dispatch. Return True if handled, False to fall through."""
    raw = await asyncio.to_thread(RouterClient.classify, text, "telegram")
    intent = raw.get("intent") or {}
    category = intent.get("category") or "chat"
    confidence = float(intent.get("confidence") or 0.0)
    params = intent.get("params") or {}

    if confidence < CONFIDENCE_THRESHOLD:
        return False  # not confident → existing NL layer takes over
    if category == "chat":
        return False

    # --- DISPATCHERS ---
    if category == "fix":
        return await _route_fix(update, context, params)
    if category == "push":
        return await _route_push(update, context, params)
    if category == "deploy":
        return await _route_deploy(update, context, params)
    if category == "query":
        return await _route_query(update, context, params)
    if category in {"finance", "crm", "calendar", "task"}:
        # Modules not yet wired — log and acknowledge so the user knows it
        # was understood, just not actioned automatically yet.
        await update.message.reply_text(
            f"Got it — categorized as `{category}`. That module isn't wired yet; "
            f"I'll log this and you can review later. (params: `{params}`)",
            parse_mode="Markdown",
        )
        return True

    return False


async def _route_fix(update, context, params: dict) -> bool:
    project = (params.get("project") or "").strip().lower()
    issue = (params.get("issue") or "").strip()
    if not project or not issue:
        return False
    proj = await asyncio.to_thread(ProjectsClient.get, project)
    if proj is None:
        await update.message.reply_text(
            f"I think you want a fix on `{project}`, but it's not in the registry. "
            f"Run /projects to see what's registered.",
            parse_mode="Markdown",
        )
        return True
    context.args = [project, "|", issue]
    await fix_command(update, context)
    return True


async def _route_push(update, context, params: dict) -> bool:
    project = (params.get("project") or "").strip().lower()
    if not project:
        return False
    context.args = [project]
    await push_command(update, context)
    return True


async def _route_deploy(update, context, params: dict) -> bool:
    project = (params.get("project") or "").strip().lower()
    branch = (params.get("branch") or "").strip()
    if not project:
        return False
    context.args = [project] + ([branch] if branch else [])
    await deploy_command(update, context)
    return True


async def _route_query(update, context, params: dict) -> bool:
    target = (params.get("target") or "").strip().lower()
    if target in {"usage", "tokens", "cost", "spend"}:
        context.args = []
        await usage_command(update, context)
        return True
    if target in {"stats", "ram", "memory", "cpu"}:
        await stats_command(update, context)
        return True
    if target in {"disk", "disks"}:
        await disks_command(update, context)
        return True
    if target in {"processes", "process", "top"}:
        context.args = []
        await processes_command(update, context)
        return True
    if target in {"vscode", "code", "windows"}:
        await vscode_command(update, context)
        return True
    if target in {"sessions", "claude", "session"}:
        await sessions_command(update, context)
        return True
    if target in {"projects", "project", "repos"}:
        await projects_command(update, context)
        return True
    if target in {"agents"}:
        await agents_command(update, context)
        return True
    return False  # don't recognize the query target; let chat handle it


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
    installed = set(RuntimeConfigService.list_ollama_models())
    configured = RuntimeConfigService.get_configured_ollama_models()
    catalog = RuntimeConfigService.build_model_catalog(active_provider=active["provider"], active_model=active["model"])

    lines = [
        f"Active model: {active['provider']} / {active['model']}",
        f"Default model: ollama / {settings.ollama_model}",
        "",
        "Model groups:",
    ]

    grouped: dict[str, list[dict[str, object]]] = {}
    for item in [*catalog["ollama_choices"], *catalog["gemini_choices"]]:
        grouped.setdefault(str(item["role_group_label"]), []).append(item)

    for group_name in ["Daily And Reports", "Coding And Websites", "Vision And Files", "Reasoning And Planning", "Cloud And Experimental", "General"]:
        items = grouped.get(group_name, [])
        if not items:
            continue
        lines.append(group_name + ":")
        for item in items:
            tags = []
            if item["active"]:
                tags.append("active")
            if item["installed"]:
                tags.append("installed")
            elif item["configured"]:
                tags.append("configured")
            if item["source"] == "cloud":
                tags.append("cloud")
            if item["cloud_auth_required"]:
                tags.append("auth")
            suffix = f" [{' | '.join(tags)}]" if tags else ""
            role_text = ", ".join(item.get("roles", [])[:3])
            lines.append(f"- {item['model']}{suffix} -> {item['summary']} ({role_text})")
        lines.append("")

    lines.append("Configured Ollama models:")
    if configured:
        lines.extend([f"- {name}" for name in configured])
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Installed Ollama models:")
    if installed:
        lines.extend([f"- {name}" for name in sorted(installed)])
    else:
        lines.append("- none yet")

    lines.extend(
        [
            "",
            "Pull ideas:",
            "- qwen3-coder:30b -> best local website and coding model",
            "- qwen2.5-coder:7b -> lighter local coding model",
            "- gemma3:12b -> stronger local screenshot and UI review",
            "- kimi-k2.5:cloud -> Ollama Cloud option, requires Ollama auth/quota",
            "",
            "Tip: use `/usemodel ollama qwen3-coder:30b` or `/usemodel ollama gemma3:4b`. Missing Ollama models will auto-pull.",
        ]
    )

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
