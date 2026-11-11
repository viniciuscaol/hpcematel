"""
Configurações da aplicação, lidas de variáveis de ambiente.
Nunca colocar senha/secret fixo aqui no código.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_base_url: str = "http://localhost:8000"
    app_name: str = "Chamados Cematel"
    database_url: str
    legacy_database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30
    environment: str = "development"

    # Pasta onde os anexos dos chamados ficam salvos no servidor.
    # Trocar esse caminho (e o volume correspondente no docker-compose)
    # é suficiente para mudar onde os arquivos são armazenados.
    anexos_dir: str = "/app/anexos"

    # WAHA (notificações WhatsApp)
    waha_api_url: str = "http://waha:3000"
    waha_api_key: str = ""
    waha_sessao: str = "default"
    waha_grupo_id: str = ""
    waha_grupo_diretoria_id: str = ""

    # Rastreio de envio/reverso via Seu Rastreio (gratuito) — vazio = recurso desligado
    # seurastreio_api_key: str = ""

    pacotevicio_api_key: str = ""

    # Monitoramento remoto (SSH); vazio desativa a coleta sem impedir o Help Desk.
    monitor_ssh_host: str = ""
    monitor_ssh_port: int = 30022
    monitor_ssh_user: str = ""
    monitor_ssh_key: str = ""
    monitor_ssh_known_hosts: str = ""
    monitor_ssh_key_passphrase: str = ""
    monitor_poll_interval: int = 5
    monitor_panic_password: str = ""
    monitor_panic_script: str = ""
    monitor_panic_sudo: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production"


settings = Settings()