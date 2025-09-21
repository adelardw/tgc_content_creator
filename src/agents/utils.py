from time import perf_counter
import uuid
import redis
import requests
from loguru import logger
import json
from datetime import datetime


def measure_time(func):

    def wrapper(*args, **kwargs):
        start = perf_counter()
        result = func(*args, **kwargs)
        time_res = perf_counter() - start
        log_data = {"node": func.__name__, "elapsed_time": f"{time_res} s", "asctime": datetime.now().isoformat()}
        logger.info(json.dumps(log_data))
        return result

    return wrapper


def links_filter(links: list[str]):
    res = []
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    if links:
        for link in links:
            try:
                answ = str(requests.get(link, headers=headers).status_code)
                if answ == '200':
                    res.append(link)
            except Exception as e:
                logger.info(f'Недоступная ссылка: {e}')
        
        return res
    else:
        return []

def redis_img_find(redis_cache: redis.StrictRedis):
    all_img_links = []
    for link in redis_cache.scan_iter("img_link_*"):
        link = redis_cache.get(link).decode()
        if link:
            all_img_links.append(link)
    
    return all_img_links

def redis_update_links(links: list[str], redis_cache: redis.StrictRedis,
                       ttl:int = 86400):
    for link in links:
        redis_cache.set(name=f'img_link_{uuid.uuid4().hex}', value=link,
                        ex=ttl)