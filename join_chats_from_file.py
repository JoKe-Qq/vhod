import asyncio
import logging
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError, InviteHashInvalidError, ChannelPrivateError
from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class JoinChatsFromFileMod(loader.Module):
    """Вступление в чаты из файла с интервалом и лимитом"""

    strings = {
        "name": "JoinChatsFromFile",
        "start_joining": "<b>Начинаю вступление в чаты...</b>",
        "joined": "<b>Вступил в чат:</b> <code>{}</code>",
        "already": "<b>Уже в чате:</b> <code>{}</code>",
        "no_tag": "<b>Нет публичного тега, пропущено:</b> <code>{}</code>",
        "error": "<b>Ошибка при вступлении в:</b> <code>{}</code> — {}",
        "done": "<b>Вступление завершено.</b>",
        "file_not_found": "<b>Файл chats_list.txt не найден!</b>",
    }

    async def joinchatscmd(self, message):
        """[интервал_сек] [лимит]
        Вступает в чаты из файла chats_list.txt с указанным интервалом и лимитом за запуск."""
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
                break
            tag = None
            if chat.startswith("https://t.me/"):
                tag = chat.split("/")[-1]
                if not tag or tag.startswith("+"):  # Приватные инвайты пропускаем
                    await utils.answer(message, self.strings("no_tag").format(chat))
                    continue
                chat_ref = "@" + tag
            elif chat.startswith("@"):
                tag = chat[1:]
                chat_ref = chat
            else:
                tag = chat
                chat_ref = chat

            if chat_ref.lower() in joined or tag.lower() in joined:
                await utils.answer(message, self.strings("already").format(chat_ref))
                continue

            if tag.startswith("+") or not tag.isalnum():
                await utils.answer(message, self.strings("no_tag").format(chat))
                continue

            try:
                await self._client(JoinChannelRequest(chat_ref))
                await utils.answer(message, self.strings("joined").format(chat_ref))
                count += 1
            except UserAlreadyParticipantError:
                await utils.answer(message, self.strings("already").format(chat_ref))
            except (InviteHashInvalidError, ChannelPrivateError):
                await utils.answer(message, self.strings("no_tag").format(chat))
            except Exception as e:
                logger.error(f"Ошибка при вступлении в {chat_ref}: {e}")
                await utils.answer(message, self.strings("error").format(chat_ref, str(e)))

            await asyncio.sleep(interval)

        await utils.answer(message, self.strings("done"))