import json
import boto3
import redis
from src.config.settings import settings


cache = redis.from_url(settings.redis_url)
s3 = boto3.client("s3", region_name=settings.aws_region)


def get_product(product_id: int):
    cached = cache.get(f"product:{product_id}")
    if cached:
        return json.loads(cached)
    return None


def set_product(product_id: int, data: dict, ttl: int = 300):
    cache.setex(f"product:{product_id}", ttl, json.dumps(data))


def upload_to_s3(bucket: str, key: str, data: bytes):
    s3.put_object(Bucket=bucket, Key=key, Body=data)
