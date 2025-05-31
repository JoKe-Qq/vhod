import asyncio
import logging
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError, InviteHashInvalidError, ChannelPrivateError
from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class JoinChatsFromFileMod(loader.Module):
    """Вступление в чаты из файла с интервалом и лимитом. 
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
    }

    async def joinchatscmd(self, message):
        """[интервал_сек] [лимит]
        Вступает в чаты из файла chats_list.txt с указанным интервалом и лимитом за запуск.
        Формат файла: id | @tag | chat_name или @tag или https://t.me/tag
        """
        args = utils.get_args(message)
        interval = int(args[0]) if len(args) > 0 else 30  # По умолчанию 30 сек.
        limit = int(args[1]) if len(args) > 1 else 10     # По умолчанию 10 чатов за запуск

        try:
            with open("chats_list.txt", "r", encoding="utf-8") as f:
                chats = [line.strip() for line in f if line.strip()]
        except Exception:
            return await utils.answer(message, self.strings("file_not_found"))

        # Получаем список диалогов, чтобы узнать где мы уже состоим
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
        await utils.answer(message, self.strings("start_joining"))
        for chat in chats:
            if count >= limit:
                await utils.answer(message, self.strings("limit_reached"))
                break

            raw = chat
            chat_ref = None
            tag = None

            # Попытка распарсить строку разного формата
            if "|" in chat:
                # Формат: id | @tag | chat_name
                parts = [p.strip() for p in chat.split("|")]
                # Ищем первую часть, начинающуюся с @, иначе вторую ссылку t.me
                tag = next((p for p in parts if p.startswith("@")), None)
                if not tag:
                    # Иногда встречаются ссылки
                    tag = next((p for p in parts if "t.me/" in p), None)
                    if tag and "t.me/" in tag:
                        # Вытаскиваем username из ссылки
                        tag_val = tag.split("t.me/")[-1]
                        if tag_val and not tag_val.startswith("+"):
                            tag = "@" + tag_val
                        else:
                            tag = None
                chat_ref = tag
            elif chat.startswith("https://t.me/"):
                tag_val = chat.split("/")[-1]
                if tag_val and not tag_val.startswith("+"):
                    tag = "@" + tag_val
                    chat_ref = tag
            elif chat.startswith("@"):
                tag = chat
                chat_ref = tag
            else:
                # Может быть просто username без @
                if chat.isalnum() and len(chat) >= 5:
                    tag = "@" + chat
                    chat_ref = tag

            if not tag or not chat_ref or tag.startswith("@+") or not tag[1:].isalnum():
                await utils.answer(message, self.strings("no_tag").format(raw))
                continue

            # Проверка — не состоим ли уже
            if chat_ref.lower() in joined or tag.lower() in joined:
                await utils.answer(message, self.strings("already").format(chat_ref))
                continue

            # Пытаемся вступить
            try:
                await self._client(JoinChannelRequest(chat_ref))
                await utils.answer(message, self.strings("joined").format(chat_ref))
                count += 1
            except UserAlreadyParticipantError:
                await utils.answer(message, self.strings("already").format(chat_ref))
            except (InviteHashInvalidError, ChannelPrivateError):
                await utils.answer(message, self.strings("no_tag").format(raw))
            except Exception as e:
                logger.error(f"Ошибка при вступлении в {chat_ref}: {e}")
                await utils.answer(message, self.strings("error").format(chat_ref, str(e)))

            await asyncio.sleep(interval)

        await utils.answer(message, self.strings("done"))
