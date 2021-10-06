from config import settings
from facebook2telegram import Facebook2Telegram

facebook_to_telegram = Facebook2Telegram(
    fb_login=settings.fb_login,
    fb_password=settings.fb_password,
    tg_token=settings.tg_token,
    tg_chat_id=settings.tg_chat_id,
)
facebook_to_telegram.update()
facebook_to_telegram.send_posts_to_telegram()
