"""Keep modern meme downloads, rendering and optional statistics resilient."""

from nonebot.exception import AdapterException, MatcherException, ProcessException
from nonebot.log import logger
from nonebot_plugin_memes.matchers import command as meme_command

from src.services.meme_avatar import MemeImageDownloadError, fetch_meme_image
from src.services.petpet import download_qq_avatar

original_image_fetch = getattr(
    meme_command, "_qqbot_original_image_fetch", meme_command.image_fetch
)
meme_command._qqbot_original_image_fetch = original_image_fetch


async def reliable_image_fetch(event, bot, state, image):
    return await fetch_meme_image(
        event, bot, state, image,
        native_fetch=original_image_fetch,
        avatar_fetch=download_qq_avatar,
    )


original_record = getattr(
    meme_command, "_qqbot_original_record", meme_command.record_meme_generation
)
meme_command._qqbot_original_record = original_record


async def reliable_record(*args, **kwargs):
    try:
        return await original_record(*args, **kwargs)
    except (MatcherException, ProcessException):
        raise
    except Exception:
        # Usage statistics are optional; a database problem must not discard a
        # successfully rendered image before the plugin gets to send it.
        logger.exception("New meme plugin: generation statistics could not be saved")


original_process = getattr(meme_command, "_qqbot_original_process", meme_command.process)
meme_command._qqbot_original_process = original_process


async def reliable_process(bot, event, state, matcher, session, meme, images, texts,
                           options=None, show_info=False):
    try:
        return await original_process(
            bot, event, state, matcher, session, meme, images, texts,
            options if options is not None else {}, show_info,
        )
    except (MatcherException, ProcessException):
        raise
    except MemeImageDownloadError:
        logger.exception("New meme plugin: image download failed")
        message = "头像或图片下载失败，请稍后重试，或直接发送图片。"
    except AdapterException:
        logger.exception("New meme plugin: image reply failed")
        message = "表情发送失败，请稍后重试。"
    except Exception:
        logger.exception("New meme plugin: rendering failed, template={}", meme.key)
        message = "表情生成失败，请稍后重试，或换一个模板。"
    try:
        await matcher.finish(message)
    except AdapterException:
        logger.exception("New meme plugin: error notice could not be sent")


meme_command.image_fetch = reliable_image_fetch
meme_command.record_meme_generation = reliable_record
meme_command.process = reliable_process
