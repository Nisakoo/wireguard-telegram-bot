import os
import httpx
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class WireguardClient(BaseModel):
    id: str
    name: str
    enabled: bool
    address: str
    publicKey: str
    createdAt: datetime
    updatedAt: datetime
    downloadableConfig: bool
    persistentKeepalive: Optional[str] = None
    latestHandshakeAt: Optional[datetime] = None
    transferRx: Optional[int] = None
    transferTx: Optional[int] = None


class WireguardAPI:
    def __init__(self, *, password: Optional[str] = None, base_url: Optional[str] = None):
        self._password = password or os.environ.get("WIREGUARD_PASSWORD")
        self._base_url = base_url or os.environ.get("WIREGUARD_BASE_URL")
        self._client: Optional[httpx.Client] = None

        if not self._password:
            raise ValueError("Password must be provided either as parameter or WIREGUARD_PASSWORD environment variable")
        if not self._base_url:
            raise ValueError("Base URL must be provided either as parameter or WIREGUARD_BASE_URL environment variable")

    def __enter__(self):
        """Входим в контекст и выполняем авторизацию"""
        self._client = httpx.Client(base_url=self._base_url)

        # Выполняем авторизацию
        auth_response = self._client.post(
            "/api/session",
            json={"password": self._password}
        )
        auth_response.raise_for_status()

        return self

    @property
    def client(self) -> httpx.Client:
        """Возвращает HTTP клиент для выполнения запросов к API"""
        if not self._client:
            raise RuntimeError("API client is not initialized. Use within context manager.")
        return self._client

    def get_clients(self) -> List[WireguardClient]:
        """Получает список всех клиентов Wireguard"""
        response = self.client.get("/api/wireguard/client")
        response.raise_for_status()

        clients_data = response.json()
        return [WireguardClient(**client_data) for client_data in clients_data]

    def get_configuration(self, client_id: str) -> str:
        """Получает конфигурационный файл для клиента по его ID"""
        response = self.client.get(f"/api/wireguard/client/{client_id}/configuration")
        response.raise_for_status()

        return response.text

    def get_qrcode(self, client_id: str) -> str:
        """Получает QR-код в формате SVG для клиента по его ID"""
        response = self.client.get(f"/api/wireguard/client/{client_id}/qrcode.svg")
        response.raise_for_status()

        return response.text

    def enable(self, client_id: str) -> None:
        """Включает клиента Wireguard по его ID"""
        response = self.client.post(f"/api/wireguard/client/{client_id}/enable")
        response.raise_for_status()

    def disable(self, client_id: str) -> None:
        """Выключает клиента Wireguard по его ID"""
        response = self.client.post(f"/api/wireguard/client/{client_id}/disable")
        response.raise_for_status()

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """Выходим из контекста и завершаем сессию"""
        if self._client:
            try:
                # Завершаем сессию
                logout_response = self._client.delete("/api/session")
                logout_response.raise_for_status()
            except Exception as e:
                # Логируем ошибку, но не прерываем выход из контекста
                print(f"Error during logout: {e}")
            finally:
                self._client.close()
                self._client = None


if __name__ == "__main__":
    with WireguardAPI() as api:
        print(api.get_clients())
