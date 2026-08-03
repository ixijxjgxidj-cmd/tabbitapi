import time
import asyncio
import hashlib
import logging
from typing import Optional, List, Dict

logger = logging.getLogger("tabbit2api")

from core.config import ConfigManager
from core.tabbit_client import TabbitClient
import core.byok_manager as byok

COOLDOWN_SECONDS = 300  # 5 分钟冷却
MAX_CONSECUTIVE_ERRORS = 3


class TokenManager:
    def __init__(self, config: ConfigManager):
        self.config = config
        self._clients: dict[str, TabbitClient] = {}
        self._indices: dict[str, int] = {}  # pool_id (user_id or "global") -> index
        self._cooldowns: dict[str, float] = {}  # token_id -> 冷却截止时间戳
        self._lock = asyncio.Lock()

    @property
    def has_global_tokens(self) -> bool:
        return len(self.config.get("tokens", default=[])) > 0

    async def _get_available_tokens(self, user_id: Optional[str] = None) -> list[dict]:
        if user_id is None:
            tokens = self.config.get("tokens", default=[])
        else:
            tokens = await byok.get_user_channels(user_id)
            
        now = time.time()
        available = []
        for t in tokens:
            if not t.get("enabled", True) and user_id is None:
                continue
            
            cooldown_until = self._cooldowns.get(t["id"], 0)
            if now >= cooldown_until:
                if t["id"] in self._cooldowns:
                    del self._cooldowns[t["id"]]
                    t["status"] = "unknown"
                    t["error_count"] = 0
                available.append(t)
        return available

    async def _get_proxy_for_user(self, user_id: str | None) -> str | None:
        proxies = self.config.get("tabbit", "outbound_proxies", default=[])
        if not proxies:
            return None
        hash_key = user_id if user_id else "global"
        assigned_proxy = await byok.assign_least_loaded_proxy(hash_key, proxies)
        return assigned_proxy

    async def _get_client(self, token_info: dict, user_id: str | None) -> TabbitClient:
        tid = token_info["id"]
        if tid not in self._clients:
            proxy_url = await self._get_proxy_for_user(user_id)
            self._clients[tid] = TabbitClient(
                token_info["value"],
                self.config.get("tabbit", "base_url"),
                self.config.get("tabbit", "client_id"),
                proxy_url=proxy_url
            )
        return self._clients[tid]

    async def get_next(self, user_id: Optional[str] = None) -> tuple[Optional[dict], Optional[TabbitClient]]:
        pool_id = user_id if user_id else "global"
        
        async with self._lock:
            available = await self._get_available_tokens(user_id)
            if not available:
                return None, None
                
            index = self._indices.get(pool_id, 0)
            index = index % len(available)
            token_info = available[index]
            self._indices[pool_id] = (index + 1) % len(available)
            client = await self._get_client(token_info, user_id)
            return token_info, client

    def report_success(self, token_id: str):
        # We don't save status to Redis immediately to avoid heavy writes on success.
        # But we do clear cooldown.
        if token_id in self._cooldowns:
            del self._cooldowns[token_id]

    def report_error(self, token_id: str):
        # Note: We track consecutive errors globally in memory for all tokens to keep it fast
        now = time.time()
        # Just simple local state modification
        for t in self.config.get("tokens", default=[]):
            if t["id"] == token_id:
                t["error_count"] = t.get("error_count", 0) + 1
                if t["error_count"] >= MAX_CONSECUTIVE_ERRORS:
                    self._cooldowns[t["id"]] = now + COOLDOWN_SECONDS
                return
                
        # If not found in global, it must be a BYOK token.
        # We don't write error counts to Redis per request, we just set local cooldown.
        # It's an approximation, but fast.
        error_counts = getattr(self, "_temp_errors", {})
        error_counts[token_id] = error_counts.get(token_id, 0) + 1
        if error_counts[token_id] >= MAX_CONSECUTIVE_ERRORS:
            self._cooldowns[token_id] = now + COOLDOWN_SECONDS
            error_counts[token_id] = 0
        setattr(self, "_temp_errors", error_counts)

    def remove_client(self, token_id: str):
        self._clients.pop(token_id, None)
        self._cooldowns.pop(token_id, None)

    def get_token_status(self, token_id: str) -> str:
        now = time.time()
        cooldown_until = self._cooldowns.get(token_id, 0)
        if now < cooldown_until:
            return "cooldown"
        return "active"

    async def close_all(self):
        for client in self._clients.values():
            await client.client.aclose()
        self._clients.clear()
