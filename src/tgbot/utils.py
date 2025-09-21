from redis import StrictRedis
import numpy as np
import os
from dotenv import load_dotenv
load_dotenv()
import pytz
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
import datetime as dt
import typing as tp
import random
import re


TELEGRAM_MAX_MESSAGE_LENGTH = 4096
TELEGRAM_MAX_MESSAGE_CAPTION = 1024

def max_day_in_month(current_year: int, current_month: int):
    '''
    Вычисляетмаксимальное количество дней в данному году и в данном месяце
    '''
    if current_year % 4 == 0 and current_month == 2:
        return 29
    if current_month <=7:
        if current_month == 2:
            return 28
        elif current_month % 2 == 0:
            return 30
        else:
            return 31
    else:
        if current_month % 2 == 0:
            return 31
        else:
            return 30

def find_tg_channels(text):
    pattern = r'@[a-zA-Z0-9_]{5,32}'
    channels = re.findall(pattern, text)
    for i, chan in enumerate(channels):
        channels[i] = chan[1:]
    return channels


def find_tg_channels_by_link(text):
    pattern = r'https://t.me/[a-zA-Z0-9_]{5,32}'
    channels = re.findall(pattern, text)
    for i, chan in enumerate(channels):
        channels[i] = chan.split('/')[-1]
    return channels

def random_next_publication_datetime(month: tp.Optional[int] = None,
                                    weekday: tp.Optional[int] = None):

    '''
    Формирует рандомную дату и время пуликации следующего пост
    '''
    curent_date = dt.datetime.now(pytz.timezone('Europe/Moscow'))
    current_weekday = dt.datetime.isocalendar(curent_date).weekday

    current_year = curent_date.year
    current_month = curent_date.month
    current_day = curent_date.day

    if month:
        assert month <= 12
        delta_publication_month = month - current_month
        delta_publication_month = delta_publication_month if delta_publication_month > 0 else 0
        next_month_publication = current_month + delta_publication_month
        random_publication_month = np.random.randint(current_month, next_month_publication if
                                                   next_month_publication != current_month \
                                                   else current_month + 1)
    else:
        pass
        random_publication_month = current_month

    if weekday:
        assert 1 <= weekday <=7
        delta_weekday = weekday - current_weekday
        delta_weekday = delta_weekday if delta_weekday > 0 else 0

        next_weekday_publication = current_weekday + delta_weekday
        random_publication_day = np.random.randint(current_day, next_weekday_publication if
                                                   next_weekday_publication != current_day \
                                                   else current_day + 1)
    else:
        max_days_in_current_month = max_day_in_month(current_year, current_month)
        random_publication_day = np.random.randint(current_day, max_days_in_current_month + 1)


    random_publication_hour = np.random.randint(0, 24)
    random_publication_minute = np.random.randint(0, 60)

    publication_date = dt.datetime(current_year, random_publication_month, random_publication_day,
                                   random_publication_hour,
                                   random_publication_minute)

    return publication_date.isoformat()


def random_next_publication_in_current_day(num_dates: tp.Optional[int] = None):


    curent_date = dt.datetime.now(pytz.timezone('Europe/Moscow'))

    current_year = curent_date.year
    current_month = curent_date.month
    current_day = curent_date.day
    current_hour = curent_date.hour
    current_minute = curent_date.minute

    possible_times = []

    for minute in range(current_minute + 1, 60):
        possible_times.append((current_hour, minute))

    for hour in range(current_hour + 1, 24):
        for minute in range(60):
            possible_times.append((hour, minute))

    if not possible_times:
        return None

    if not num_dates:

        pub_hour, pub_minute = random.choice(possible_times)

        publication_date = dt.datetime(
            current_year, current_month, current_day,
            pub_hour, pub_minute,
            tzinfo=curent_date.tzinfo
        )
        return publication_date

    else:
        if num_dates > len(possible_times):
            raise ValueError(
                f"Невозможно сгенерировать {num_dates} уникальных дат. "
                f"До конца дня осталось только {len(possible_times)} свободных минут."
            )


        selected_times = random.sample(possible_times, num_dates)


        publication_dates = [
            dt.datetime(
                current_year, current_month, current_day,
                hour, minute,
                tzinfo=curent_date.tzinfo
            ) for hour, minute in selected_times
        ]

        return publication_dates


def random_next_publication_in_current_hour(num_dates: tp.Optional[int] = None):


    curent_date = dt.datetime.now(pytz.timezone('Europe/Moscow'))

    current_year = curent_date.year
    current_month = curent_date.month
    current_day = curent_date.day
    current_hour = curent_date.hour
    current_minute = curent_date.minute

    possible_times = []

    for minute in range(current_minute + 1, 60):
        possible_times.append((current_hour, minute))

    if not possible_times:
        return None

    if not num_dates:

        pub_hour, pub_minute = random.choice(possible_times)

        publication_date = dt.datetime(
            current_year, current_month, current_day,
            pub_hour, pub_minute,
            tzinfo=curent_date.tzinfo)
        return [publication_date]

    else:
        if num_dates > len(possible_times):
            raise ValueError(
                f"Невозможно сгенерировать {num_dates} уникальных дат. "
                f"До конца дня осталось только {len(possible_times)} свободных минут."
            )


        selected_times = random.sample(possible_times, num_dates)


        publication_dates = [
            dt.datetime(
                current_year, current_month, current_day,
                hour, minute,
                tzinfo=curent_date.tzinfo
            ) for hour, minute in selected_times
        ]

        return publication_dates


def filter_message(text: str):
    '''
    Мб что - то ещё добавится
    '''
    return text.replace("*"," ")

def split_short_long_message(text: str, max_length_caption: int = TELEGRAM_MAX_MESSAGE_CAPTION,
                             second_part_percent_value_threshold: int = 0.3):
    '''
    second_part_percent_value_threshold - размер второй части сплита от max_length_caption
    если вторая часть больше second_part_percent_value_threshold*second_part_percent_value_threshold, то 
    есть смысл разбивать пост и прикладывать картинку
    иначе - нет, картинка в кэшэ
    '''

    if len(text) <= max_length_caption:
        return text, None
    elif len(text) >= (1 + second_part_percent_value_threshold)*max_length_caption:
        short_part_part = text[: max_length_caption]
        pos_space_num = short_part_part.rfind(' ')
        if pos_space_num != -1:
            short_part = text[:pos_space_num]
            long_part = text[pos_space_num:]
            return short_part, long_part
        else:
            return None # если порог выбрали неверно, слишком маленьким например, то проще картинку не вставлять,\
                        # но это условие почти всегда не выполняется, так как порог фиксирован
    else:
        # если на второй части длина меньше
        return None
        
        

def split_long_message(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """
    "Умно" разбивает длинное сообщение на несколько частей, не разрывая слова.
    Возвращает список сообщений (частей).
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    words = text.split(' ')

    for word in words:
        if len(current_chunk) + len(word) + 1 > max_length:
            chunks.append(current_chunk.strip())
            current_chunk = ""

        current_chunk += word + " "

    if current_chunk:
        chunks.append(current_chunk.strip().replace("*"," "))

    return chunks

class HFLCSSimTexts:

    embed_model: str = os.getenv('EMBED_MODEL','cointegrated/LaBSE-en-ru')
    model_kwargs = {'device': 'cpu'}
    encode_kwargs = {'normalize_embeddings': True}

    embed = HuggingFaceEmbeddings(model_name=embed_model,
                                 model_kwargs=model_kwargs,
                                 encode_kwargs=encode_kwargs)

    def cossine_simmilar(self, input_text: str, target_text: str):

        embed_input = np.array(self.embed.embed_query(input_text))
        embed_target = np.array(self.embed.embed_query(target_text))

        return (embed_input * embed_target).sum()

def find_dublicates(embedder: HFLCSSimTexts, cache: StrictRedis, post: str,
                      threshold: float = 0.7):
    
    for key in cache.scan_iter(match='post_*'):
        cached_post = cache.get(key).decode()
        
        if embedder.cossine_simmilar(post, cached_post) >= threshold:
            return True
    
    return False

def find_ads(post: str):
    key_words = ['реклама','erid']    
    for k in key_words:
        if k in post.lower():
            return True
    
    return False