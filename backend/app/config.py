from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    nebius_api_key: str
    nebius_base_url: str = "https://api.studio.nebius.com/v1/"
    nebius_llm_model: str = "Qwen/Qwen2.5-72B-Instruct-fast"
    nebius_embedding_model: str = "BAAI/bge-en-icl"
    nebius_embedding_dim: int = 4096

    pinecone_api_key: str
    pinecone_index_name: str
    pinecone_namespace: str = "patisserie"
    pinecone_semantic_namespace: str = "patisserie-semantic"

    bm25_index_path: str = "data/bm25_index.pkl"
    thresholds_path: str = "data/thresholds.json"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
