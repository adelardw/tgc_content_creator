import redis
import numpy as np
np.random.seed(131200)

cache_db = redis.StrictRedis(host='localhost',port=6379,
                             db=13)