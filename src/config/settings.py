from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "production-python-app"
    db_url: str = "postgresql://postgres:postgres@localhost:5432/appdb"
    redis_url: str = "redis://localhost:6379"
    aws_region: str = "us-east-1"
    secret_key: str = "changeme"

    class Config:
        env_file = ".env"


settings = Settings()
