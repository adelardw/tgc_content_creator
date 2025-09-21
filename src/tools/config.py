import os
from dotenv import load_dotenv
import yaml
from omegaconf import DictConfig,OmegaConf
import typing as tp
load_dotenv()


GENERAL_SAVE_PATH = os.path.abspath(os.path.curdir)
CONFIG_PATH = os.path.join(GENERAL_SAVE_PATH, 'config.yml')
TIMEZONE = 'Europe/Moscow'
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
CX_ID = os.getenv('CX_ID')

with open(CONFIG_PATH, 'r') as file:

    data = DictConfig(yaml.safe_load(file))
    user_agents = data.metadata.web.user_agents
    endpoints = data.metadata.web.tgstat_endpoints
    web_retrieve_kwargs = data.metadata.web_retrieve_kwargs

def save_yaml(input_data: tp.Any, saved_key: str = 'user_agents'):
    data.metadata.web[saved_key] = input_data
    config = OmegaConf.create(data)
    OmegaConf.save(config, CONFIG_PATH)


