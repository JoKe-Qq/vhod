import asyncio
import logging
import random
import re
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError, InviteHashInvalidError, ChannelPrivateError, FloodWaitError
from .. import loader, utils

logger = logging.getLogger(__name__)

USERNAME_RE = re.compile(r"^@[A-Za-z0-9_]{5,32}$")

@loader.tds
class JoinChatsFromFileMod(loader.Module):
    """Вступление в чаты из файла с рандомной задержкой и лимитом.
    Формат строки: id | @tag | chat_name или просто @tag/ссылка"""

    strings = {
        "name": "JoinChatsFromFile",
        "start_joining": "<b>Начинаю вступление в чаты...</b>",
        "joined": "<b>Вступил в чат:</b> <code>{}</code>",
        "already": "<b>Уже в чате:</b> <code>{}</code>",
        "no_tag": "<b>Нет публичного тега, пропущено:</b> <code>{}</code>",
        "error": "<b>Ошибка при вступлении в:</b> <code>{}</code> — {}",
        "done": "<b>Вступление завершено.</b>",
        "file_not_found": "<b>Файл chats_list.txt не найден!</b>",
        "invalid_tag": "<b>Некорректная строка, пропущено:</b> <code>{}</code>",
        "limit_reached": "<b>Достигнут лимит вступлений за один запуск.</b>",
        "floodwait": "<b>FloodWait! Ожидаю {} сек перед продолжением...</b>",
        "stopped": "<b>Вступление остановлено пользователем.</b>",
        "not_running": "<b>Нет активного процесса вступления.</b>",
        "progress": "<b>Вступаю в чаты: {}/{} ({:.1f}%)</b>",
    }

    def __init__(self, *a, **kw):
        self._join_task = None
        super().__init__(*a, **kw)

    async def joinchatscmd(self, message):
        """[мин_интервал] [макс_интервал] [лимит]
        Вступает в чаты из файла chats_list.txt с указанным рандомным интервалом (секунды) и лимитом за запуск.
        Пример: .joinchats 30 60 10"""
        if self._join_task is not None and not self._join_task.done():
            return await utils.answer(message, "<b>Уже выполняется процесс вступления!</b>")

        args = utils.get_args(message)
        min_interval = int(args[0]) if len(args) > 0 else 30
        max_interval = int(args[1]) if len(args) > 1 else 60
        limit = int(args[2]) if len(args) > 2 else 10

        if max_interval < min_interval:
            min_interval, max_interval = max_interval, min_interval

        async def joiner():
            try:
                with open("chats_list.txt", "r", encoding="utf-8") as f:
                    chats = [line.strip() for line in f if line.strip()]
            except Exception:
                await utils.answer(message, self.strings("file_not_found"))
                return

            dialogs = await self._client.get_dialogs()
            joined = set()
            for d in dialogs:
                if d.is_channel or d.is_group:
                    username = getattr(d.entity, "username", None)
                    if username:
                        joined.add("@" + username.lower())
                    elif getattr(d.entity, "id", None):
                        joined.add(str(d.entity.id))

            count = 0
            total = len(chats)
            await utils.answer(message, self.strings("start_joining"))
            for idx, chat in enumerate(chats, 1):
                if self._join_task is None or self._join_task.cancelled():
                    await utils.answer(message, self.strings("stopped"))
                    return
                if count >= limit:
                    await utils.answer(message, self.strings("limit_reached"))
                    break

                raw = chat
                chat_ref = None
                tag = None

                # Парсим строку любого формата
                if "|" in chat:
                    parts = [p.strip() for p in chat.split("|")]
                    tag = next((p for p in parts if p.startswith("@")), None)
                    if not tag:
                        tag = next((p for p in parts if "t.me/" in p), None)
                        if tag and "t.me/" in tag:
                            tag_val = tag.split("t.me/")[-1].split("?")[0]
                            if tag_val and not tag_val.startswith("+"):
                                tag = "@" + tag_val
                            else:
                                tag = None
                    chat_ref = tag
                elif chat.startswith("https://t.me/"):
                    tag_val = chat.split("/")[-1].split("?")[0]
                    if tag_val and not tag_val.startswith("+"):
                        tag = "@" + tag_val
                        chat_ref = tag
                elif chat.startswith("@"):
                    tag = chat
                    chat_ref = tag
                else:
                    if chat.isalnum() and len(chat) >= 5:
                        tag = "@" + chat
                        chat_ref = tag

                if not tag or not chat_ref or tag.startswith("@+") or not USERNAME_RE.match(tag):
                    await utils.answer(message, self.strings("no_tag").format(raw))
                    continue

                if chat_ref.lower() in joined or tag.lower() in joined:
                    await utils.answer(message, self.strings("already").format(chat_ref))
                    continue

                try:
                    await self._client(JoinChannelRequest(chat_ref))
                    await utils.answer(message, self.strings("joined").format(chat_ref))
                    count += 1
                except UserAlreadyParticipantError:
                    await utils.answer(message, self.strings("already").format(chat_ref))
                except (InviteHashInvalidError, ChannelPrivateError):
                    await utils.answer(message, self.strings("no_tag").format(raw))
                except FloodWaitError as e:
                    await utils.answer(message, self.strings("floodwait").format(e.seconds))
                    await asyncio.sleep(e.seconds)
                    continue
                except Exception as e:
                    logger.error(f"Ошибка при вступлении в {chat_ref}: {e}")
                    await utils.answer(message, self.strings("error").format(chat_ref, str(e)))

                await utils.answer(
                    message,
                    self.strings("progress").format(idx, total, idx / total * 100)
                )
                # Рандомная задержка
                delay = random.randint(min_interval, max_interval)
                await asyncio.sleep(delay)

            await utils.answer(message, self.strings("done"))
            self._join_task = None

        self._join_task = asyncio.create_task(joiner())

    async def joinstopcmd(self, message):
        """Остановить процесс вступления в чаты"""
        if self._join_task is not None and not self._join_task.done():
            self._join_task.cancel()
            self._join_task = None
            await utils.answer(message, self.strings("stopped"))
        else:
            await utils.answer(message, self.strings("not_running"))
