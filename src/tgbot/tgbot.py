import asyncio
from collections import deque
from aiogram import Bot
from aiogram.types import KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram import F
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart, Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from dotenv import load_dotenv,find_dotenv
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
import typing as tp


import datetime as dt
import pytz
import os

from src.tgbot.cache import cache_db
from src.agents.source_agent_graph import graph
from src.agents.prompts import FORBIDDEN_ANSWER
from src.tgbot.bot_schemas import BotStates
from src.tgbot.utils import (split_long_message, random_next_publication_in_current_hour,
                             split_short_long_message,
                            find_tg_channels_by_link, find_tg_channels, find_dublicates,find_ads,
                            HFLCSSimTexts)

from src.tools.telegram_web_search import get_channel_posts, find_channel_names, get_channel_single_post_info
from src.tools.config import tgc_search_kwargs

import pytz


load_dotenv(find_dotenv('.env'))

API_TOKEN = os.getenv('TGBOTAPIKEY', None)
ADMIN_ID = os.getenv('ADMINID', None)
CHANNEL_ID = os.getenv('CHANNEL_ID')
TIMEZONE = pytz.timezone(os.getenv('TIMEZONE'))

embedder=HFLCSSimTexts()
storage=MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)


def prepare_messages(post: str):
    long_short_message = split_short_long_message(post)
    results = []
    if long_short_message:
        short, long = long_short_message
        results.append(short)
        if long:
            chunks = split_long_message(long)
            results.extend(chunks)
        
        return results, True
    else:
        results.append(post)
        return results, False
                

async def send_post_to_channel(bot: Bot, channel_id: str, post_text: str, image_link: tp.Optional[str]):
    """
    Функция, которая отправляет пост в канал, С УЧЕТОМ ОГРАНИЧЕНИЯ ДЛИНЫ.
    """
    try:
        message_chunks, need_photo_to_msg_chunk = prepare_messages(post_text)
        for i, chunk in enumerate(message_chunks):
            if i == 0:
                if image_link and need_photo_to_msg_chunk:
                    await bot.send_photo(chat_id=channel_id, photo=image_link, caption=chunk)
                else:
                    await bot.send_message(chat_id=channel_id, text=chunk)    
            else:        
                await bot.send_message(chat_id=channel_id, text=chunk)
    except Exception as e:
        logger.critical(f"Ошибка при отправке поста в канал {channel_id}: {e}")


async def auto_send_posts(bot: Bot, channel_id: int | str, state: FSMContext):
    """Автоматически отправляет посты в канал"""

    data = await state.get_data()
    generated_posts = data.get('generated_posts', deque())
    images_links = data.get('images_links', deque())
    if generated_posts:
        for post,image_link in zip(generated_posts, images_links):
            await send_post_to_channel(bot, channel_id, post, image_link)
            await asyncio.sleep(64)




async def show_next_post(message: types.Message, state: FSMContext):
    """
    Показывает следующий пост из очереди. Эта функция теперь центральная.
    """
    data = await state.get_data()
    generated_posts = data.get('generated_posts', deque())
    images_links = data.get('images_links', deque())

    if generated_posts:
        post_to_show = generated_posts[0]
        if images_links:
            image_link = images_links[0]

        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(text="✅ Подтвердить запись"),
                    KeyboardButton(text="❌ Отвергнуть"))
        
        message_chunks, need_photo_to_msg_chunk = prepare_messages(post_to_show)
        for i, chunk in enumerate(message_chunks):
            is_last_chunk = (i == len(message_chunks) - 1)
            reply_markup = builder.as_markup(resize_keyboard=True, one_time_keyboard=True) if is_last_chunk else None
            if i == 0:
                if image_link and need_photo_to_msg_chunk:
                    await message.answer_photo(photo=image_link,
                                           caption=chunk, reply_markup=reply_markup)
                else:
                    await message.answer(text=chunk, reply_markup=reply_markup)    
            else:        
                await message.answer(text=chunk, reply_markup=reply_markup)

        await state.set_state(BotStates.post_confirmation)
    else:
        await message.answer('Все посты обработаны!', reply_markup=ReplyKeyboardRemove())
        await state.clear()
        await cmd_menu(message)



@router.message(CommandStart())
@router.message(Command('menu'))
async def cmd_menu(message: types.Message):

    user_id = message.from_user.id
    builder = ReplyKeyboardBuilder()
    #builder.row(KeyboardButton(text="✍️♾️ Найти ТГК и переписать посты"))
    builder.row(KeyboardButton(text="✍️ Переписать пост"))
    builder.row(KeyboardButton(text="✍️✈️ Переписать посты по заданным каналам"))
    builder.row(KeyboardButton(text="✍️🕸️🌏 WebRag"))
    builder.row(KeyboardButton(text="✍️✈️ (AUTOMATIC) Переписать посты по заданным каналам"))
    builder.row(KeyboardButton(text="🤖💬 Получить последнюю генерацию поста"))
    builder.row(KeyboardButton(text="Develop: Получить аналитику по каналу"))

    if user_id == ADMIN_ID:
        builder.row(KeyboardButton(text="➕ Добавить нового админа в ТГК"))
        builder.row(KeyboardButton(text="🧑‍💻 Поменять пароль у администратора"))
        builder.row(KeyboardButton(text="🆔 Сменить идентификатор администратора"))
    await message.answer(
        "Выберите действие:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@router.message(F.text == '✍️♾️ Найти ТГК и переписать посты')
async def write_post_theme_multiple(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.theme_user_message)
    await message.answer('Отлично! Жду тему для серии постов',
                          reply_markup=ReplyKeyboardRemove())

@router.message(F.text == '✍️ Переписать пост')
async def rewrite_replyed_post(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.rewrite_replyed_post)
    await message.answer('Отлично! Жду пересланный пост / сообщение из ТГК!',
                          reply_markup=ReplyKeyboardRemove())


@router.message(F.text == '✍️✈️ Переписать посты по заданным каналам')
async def rewrite_channels_post(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.rewrite_follow_channel_post)
    await message.answer("Отлично! Названия каналов!"\
                            "Требуемый формат записи каналов:"\
                            "@название канала 1, @название канала 2, ..., @название канала k."\
                            "Либо пересылайте ссылки на каналы в виде:"\
                            "https://t.me/<имя канала>",
                          reply_markup=ReplyKeyboardRemove())




@router.message(F.text == '✍️🕸️🌏 WebRag')
async def write_post_theme_single(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.theme_user_message_rag)
    await message.answer('Отлично! Жду тему для генерации одного поста с использованием поисковика',
                          reply_markup=ReplyKeyboardRemove())


@router.message(F.text == '✍️✈️ (AUTOMATIC) Переписать посты по заданным каналам')
async def auto_write_post_theme_single(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.auto_rewrite_follow_channel_post)
    await message.answer("Отлично! Названия каналов!"\
                            "Требуемый формат записи каналов:"\
                            "@название канала 1, @название канала 2, ..., @название канала k."\
                            "Либо пересылайте ссылки на каналы в виде:"\
                            "https://t.me/<имя канала>",
                          reply_markup=ReplyKeyboardRemove())



@router.message(BotStates.rewrite_replyed_post)
async def rewrite_replyed_post_handler(message: types.Message, state: FSMContext):
    '''
    Переписывает пост который пришел через пересылку
    '''
    user_id = message.from_user.id
    config = {"configurable": {"thread_id": user_id}}
    original_message_id = message.forward_from_message_id
    source_chat = message.forward_from_chat
    post_link = f"https://t.me/{source_chat.username}/{original_message_id}"



    channel_post = get_channel_single_post_info(source_chat.username, original_message_id)
    try:
        post = channel_post['text']
        await message.answer(f'Post URL: {post_link}')
        emoji_reactions = channel_post['reactions']
        generated_post = graph.invoke({'post': post,'emoji_reactions':emoji_reactions,
                                "is_replyed_message": True},config = config)

        
        cache_db.set(name=f'post_{post_link}', value=post,
                                ex=24 * 60 * 60 )

        dates = random_next_publication_in_current_hour(1)
        await state.update_data(generated_posts=deque([generated_post['generation']]))
        await state.update_data(post_datetime_publication=deque(dates))
        await state.update_data(images_links=deque([generated_post['image_url']]))
        await show_next_post(message, state)
    except Exception as e:
        return



@router.message(BotStates.rewrite_follow_channel_post)
async def rewrite_channels_post_handler(message: types.Message, state: FSMContext):
    '''
    Переписывает посты рассматрыиваемых каналов
    '''
    user_id = message.from_user.id
    config = {"configurable": {"thread_id": user_id}}
    text = message.text
    results = []
    images_links = []
    channel_by_link = find_tg_channels_by_link(text)
    channels_by_endpoints = find_tg_channels(text)
    channels_result = channel_by_link + channels_by_endpoints

    if channels_result:
        await message.answer(f'Я смог найти следующие названия ТГК: {", ".join(channels_result)}',
                          reply_markup=ReplyKeyboardRemove())
        for chan in channels_result:
            last_posts = get_channel_posts(chan, k=tgc_search_kwargs['max_post_per_channel'])
            for posts in last_posts:
                is_ads = posts['is_ads']
                if not is_ads:
                    post = posts['text']
                    emoji_reactions = posts['reactions']

                    dublcate_cond = find_dublicates(embedder, cache_db, post, 0.7)
                    ads_cond = find_ads(post)
                    if not dublcate_cond and not ads_cond:
                        result = graph.invoke({'post': post,'emoji_reactions': emoji_reactions,
                                        'is_selected_channels': True}
                                        ,config=config)


                        results.append(result['generation'])
                        images_links.append(result['image_url'])
                        cache_db.set(f'post_{posts['post_url']}', post,
                                    ex=24 * 60 * 60 )
                    else:
                        continue

        if results:
            num_dates = len(results)
            dates = random_next_publication_in_current_hour(num_dates)

            await state.update_data(images_links=deque(images_links))
            await state.update_data(generated_posts=deque(results))
            await state.update_data(post_datetime_publication=deque(dates))

            await show_next_post(message, state)
        else:
            await message.answer("Упс, вероятно все посты были дубликатами. Попробоуйте снова",
                          reply_markup=ReplyKeyboardRemove())
            await cmd_menu(message)
    else:
        await message.answer("Не смог найти телеграм каналы. Пожалуйста, следуйте шаблону выше",
                          reply_markup=ReplyKeyboardRemove())
        await cmd_menu(message)




@router.message(BotStates.theme_user_message)
async def theme_handler(message: types.Message, state: FSMContext):
    '''
    Определяет нужный эндпоинт (тему различных тгк) из ТГСТАТА
    '''
    
    user_id = message.from_user.id
    config = {"configurable": {"thread_id": user_id}}
    msg_id = message.message_id
    time_ = dt.datetime.now(tz=TIMEZONE).isoformat()

    msg_id = 't_' + str(msg_id) + f'_time: {time_}'
    theme = message.text
    if theme:
        cache_db.set(msg_id, theme)
        await state.update_data(theme=theme)
        await message.answer('👀 Находим нужный endpoint ...',
                           reply_markup=ReplyKeyboardRemove())

        choice_endpoint = graph.invoke({'user_message': theme},config=config)
        gen = choice_endpoint.get('generation', None)
        if gen and gen == FORBIDDEN_ANSWER:
            await message.answer('Извините, но по Ваш запрос не валиден',
                               reply_markup=ReplyKeyboardRemove())
            await state.clear()
            await cmd_menu(message)
        else:
            telegram_channels = find_channel_names(choice_endpoint['endpoint'])
            builder = ReplyKeyboardBuilder()

            if telegram_channels:

                for channel in telegram_channels:
                    builder.add(KeyboardButton(text=f"✍️ {channel}"))

                builder.adjust(2)
                await message.answer('Выберите телеграм канал из списка',
                                reply_markup=builder.as_markup(resize_keyboard=True))
                builder.row(KeyboardButton(text="⬅️ Назад"))
                await state.set_state(BotStates.select_channel)
            else:
                await message.answer('Извините, но по Ваш запрос не валиден',
                                reply_markup=ReplyKeyboardRemove())

                await state.clear()
                await cmd_menu(message)
    else:
        await message.answer('Пожалуйста, введите запрос.',
                            reply_markup=ReplyKeyboardRemove())

@router.message(BotStates.select_channel, F.text)
async def select_channel_name(message: types.Message, state: FSMContext):
    '''
    Когда нашли тему - эндпоинт под ТГСТАТ исходя из запроса пользователя, 
    то предлагаем ему список найденных ТГК в данной теме, откуда пользователь сам выберет нужный канал
    '''
    user_id = message.from_user.id
    config = {"configurable": {"thread_id": user_id}}
    selected_button_text = message.text
    if selected_button_text.startswith("✍️ "):
        channel_name = selected_button_text.replace("✍️ ", "").strip()
    else:
        channel_name = selected_button_text.strip()

    await message.answer(f'Переписываем из канала {channel_name} последние новости ...',
                           reply_markup=ReplyKeyboardRemove())

    results = []
    images_links = []
    if channel_name.startswith('@'):
        channel_name = channel_name[1:]
    channel_posts = get_channel_posts(channel_name, k=tgc_search_kwargs['max_post_per_channel'])
    for channel_post in channel_posts:

        is_ads = post['is_ads']
        if not is_ads:
            post = channel_post['text']
            emoji_reactions = channel_post['reactions']
            ads_cond = find_ads(post)
            if not ads_cond:
                result = graph.invoke({'post': post,'emoji_reactions': emoji_reactions,
                                        'is_selected_channels': True}
                                        ,config=config)

                results.append(result['generation'])
                images_links.append(result['image_url'])
                cache_db.set(f'post_{channel_post['post_url']}', post,
                                ex=24 * 60 * 60 )



    num_dates = len(results)
    dates = random_next_publication_in_current_hour(num_dates)
    await state.update_data(images_links=deque(images_links))
    await state.update_data(generated_posts=deque(results))
    await state.update_data(post_datetime_publication=deque(dates))

    await show_next_post(message, state)


@router.message(BotStates.theme_user_message_rag)
async def theme_rag_handler(message: types.Message, state: FSMContext):
    '''
    Генерация по поиску в интернете (парсинг + online RAG)
    '''
    msg_id = message.message_id
    user_id = message.from_user.id
    config = {"configurable": {"thread_id": user_id}}

    time_ = dt.datetime.now(tz=TIMEZONE).isoformat()

    msg_id = 't_' + str(msg_id) + f'_time: {time_}'
    theme = message.text
    if theme:

        cache_db.set(msg_id, theme)
        await state.update_data(theme=theme)
        await message.answer('Генерируем пост с поиском запроса в интернете ...',
                            reply_markup=ReplyKeyboardRemove())

        generated_post = graph.invoke({'user_message':theme,'add_web_parsing_as_ctx': True},
                                      config=config)
    

        dates = random_next_publication_in_current_hour(1)
        await state.update_data(generated_posts=deque([generated_post['generation']]))
        await state.update_data(images_links=deque([generated_post['image_url']]))
        await state.update_data(post_datetime_publication=deque(dates))
        await show_next_post(message, state)
    else:
        await message.answer('Пожалуйста, введите запрос.',
                            reply_markup=ReplyKeyboardRemove())



@router.message(BotStates.post_confirmation, F.text == '✅ Подтвердить запись')
async def post_acception(message: types.Message, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
    """
    Подтверждение записи
    """
    data = await state.get_data()
    post_to_send = data.get('generated_posts', deque())
    images_links = data.get('images_links', deque())
    time_to_post = data.get('post_datetime_publication', deque())

    if not post_to_send:
        await message.answer("Ошибка: не найдено постов для подтверждения.")
        await state.clear()
        await cmd_menu(message)

    post = post_to_send.popleft()
    image_link = images_links.popleft()
    if time_to_post:
        dt_post = time_to_post.popleft()
        await state.update_data(post_datetime_publication=time_to_post)
    else:
        dt_now = dt.datetime.now(TIMEZONE)
        dt_post = dt_now + dt.timedelta(minutes=2)
        
    await state.update_data(generated_posts=post_to_send)
    await state.update_data(images_links=images_links)

    msg_id = message.message_id
    pst_id = 'p_' + str(msg_id) + f'_time: {dt_post.isoformat()}'

    cache_db.set(pst_id, post)
    scheduler.add_job(
                send_post_to_channel,
                trigger='date',
                run_date=dt_post,
                kwargs={
                'bot': bot,
                'channel_id': CHANNEL_ID,
                'post_text': post,
                'image_link': image_link})

    await message.answer(f"✅ Пост запланирован на {dt_post.strftime('%H:%M:%S')}")
    await show_next_post(message, state)




@router.message(BotStates.post_confirmation, F.text=='❌ Отвергнуть')
async def post_reject(message:types.Message, state: FSMContext):
    """
    Отклонение записи
    """
    data = await state.get_data()
    post_to_send = data.get('generated_posts',deque())
    time_to_post = data.get('post_datetime_publication', deque())
    images_links = data.get('images_links', deque())

    post_to_send.popleft()
    images_links.popleft()
    if time_to_post:
        time_to_post.popleft()
        await state.update_data(post_datetime_publication=time_to_post)

    await state.update_data(generated_posts=post_to_send)
    await state.update_data(images_links=images_links)
    
    await message.answer(
        "Запись отклонена!",
        reply_markup=ReplyKeyboardRemove())

    await show_next_post(message, state)


@router.message(F.text == '🤖💬 Получить последнюю генерацию поста')
async def get_latest_llm_message(message:types.Message):
    """
    Получение последнего сгенерированного сообщения
    """
    youngest_time = None

    for key in cache_db.scan_iter(match='p*'):
        if key:
            time_str = key.decode().split(': ', 1)[-1]
            current_time = dt.datetime.fromisoformat(time_str)
            if youngest_time is None or current_time > youngest_time:
                youngest_time = current_time
                youngest_record = key.decode()

    yongest_rec = cache_db.get(youngest_record)
    if yongest_rec:
        await message.answer('Последняя сгенерированная запись',
                        reply_markup=ReplyKeyboardRemove())

        await message.answer(yongest_rec)
        await cmd_menu(message)
    else:
        await message.answer('Нет записей!')
        await cmd_menu(message)


# на это ставим скеудлер
async def channel_look_up(channels: list, config: dict,
                          storage: BaseStorage, bot: Bot,
                          user_id: int | str, chat_id: int | str):
    
    '''
    Автоматический парс + генерация + публикация
    '''

    posts_to_rewtire = []
    images_links = []
    for chan in channels:
        last_posts = get_channel_posts(chan, k=tgc_search_kwargs['max_post_per_channel'])
        for posts in last_posts:
            url = posts['post_url']
            if cache_db.get(f'post_{url}'):
                continue
            else:
                is_ads = posts['is_ads']
                if not is_ads:
                    post = posts['text']
                    emoji_reactions = posts['reactions']
                    dublcate_cond = find_dublicates(embedder, cache_db, post, 0.7)
                    ads_cond = find_ads(post)
                    if not dublcate_cond and not ads_cond:
                        result = graph.invoke({'post': post,'emoji_reactions': emoji_reactions,
                                        'is_selected_channels': True},config=config)

                        posts_to_rewtire.append(result['generation'])
                        images_links.append(result['image_url'])

                        cache_db.set(f'post_{url}', post,
                                    ex=24 * 60 * 60 )
                    
                    
                    else:
                        logger.info(f'FIND DUBLICATES: {dublcate_cond}; FIND ADDS: {ads_cond}; ')
                        continue
                else:
                    logger.info('ADS POST')
                    continue

    if posts_to_rewtire:
        state_key = StorageKey(bot_id=bot.id, user_id=user_id, chat_id=chat_id)
        state = FSMContext(storage=storage, key=state_key)
        await state.update_data(generated_posts=deque(posts_to_rewtire))
        await state.update_data(images_links=deque(images_links))
        await auto_send_posts(bot, CHANNEL_ID, state)


@router.message(BotStates.auto_rewrite_follow_channel_post)
async def auto_rewrite_channels_post_handler(message: types.Message, storage: BaseStorage,
                                             bot: Bot,
                                             scheduler: AsyncIOScheduler):
    
    '''
    Поиск из запроса пользователя ТГК
    '''
    user_id = message.from_user.id
    chat_id = message.chat.id

    config = {"configurable": {"thread_id": user_id}}
    text = message.text
    channel_by_link = find_tg_channels_by_link(text)
    channels_by_endpoints = find_tg_channels(text)
    channels_result = channel_by_link + channels_by_endpoints

    if channels_result:
        await message.answer(f'Я смог найти следующие названия ТГК: {", ".join(channels_result)}',
                                                                reply_markup=ReplyKeyboardRemove())
    

        scheduler.add_job(
                channel_look_up,
                trigger='interval',
                #hour='6-23',
                #minute='*/5',
                minutes=5,
                id=f"channel_lookup_{user_id}",
                kwargs={
                    'channels': channels_result,
                    'config': config,
                    'bot': bot,
                    'user_id':user_id,
                    'chat_id': chat_id,
                    'storage':storage})
    else:
        await message.answer("Не смог найти телеграм каналы. Пожалуйста, следуйте шаблону выше",
                          reply_markup=ReplyKeyboardRemove())


async def change_tgc_admin_password():
    pass

async def add_tgc_new_admin():
    pass

async def main():
    logger.info('StartApp')
    scheduler = AsyncIOScheduler(timezone=os.getenv('TIMEZONE'))
    scheduler.start()
    await dp.start_polling(bot, scheduler=scheduler, storage=storage)
