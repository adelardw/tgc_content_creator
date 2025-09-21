from aiogram.fsm.state import State, StatesGroup


class BotStates(StatesGroup):
    select_channel = State()
    rewrite_replyed_post = State()
    rewrite_follow_channel_post = State()
    theme_user_message_rag = State()
    theme_user_message = State()
    post_confirmation = State()
    auto_rewrite_follow_channel_post = State()