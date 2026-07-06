import os


class Settings:
    def __init__(self) -> None:
        # Cleanlist threshold (Tarea 0b). Days since mtime to consider a file "cold/removable".
        self.cleanlist_days: int = int(os.getenv("CLEANLIST_DAYS", "365"))
        self.db_path: str = os.getenv("DB_PATH", "/config/data/myfolder.db")
        self.hash_db_path: str = os.getenv("HASH_DB_PATH", "/config/data/hashes.db")
        self.data_root: str = os.getenv("DATA_ROOT", "/data")
        self.reindex_hour: int = int(os.getenv("REINDEX_HOUR", "13"))
        self.reindex_max_age_h: int = int(os.getenv("REINDEX_MAX_AGE_H", "24"))
        self.auto_reindex: bool = os.getenv("AUTO_REINDEX", "1") == "1"
        # /etc/passwd y /etc/group del HOST (montados ro en el contenedor)
        # para resolver UID/GID a nombres reales del NAS al indexar.
        self.host_passwd: str = os.getenv("HOST_PASSWD", "/host/etc/passwd")
        self.host_group: str = os.getenv("HOST_GROUP", "/host/etc/group")


settings = Settings()
