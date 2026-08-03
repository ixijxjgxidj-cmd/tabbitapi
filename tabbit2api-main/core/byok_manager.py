import os
import json
import time
import uuid
import logging
import asyncio
from typing import List, Dict, Optional
import redis.asyncio as redis

from core.encryption import encrypt_token, decrypt_token

logger = logging.getLogger("tabbit2openai")

# L1 Cache: user_id -> List[Dict]
_L1_CACHE: Dict[str, List[Dict]] = {}
_REDIS_CLIENT: Optional[redis.Redis] = None
_PUBSUB_TASK: Optional[asyncio.Task] = None

async def init_byok_manager():
    """Initialize Redis connection and start Pub/Sub listener."""
    global _REDIS_CLIENT, _PUBSUB_TASK
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    try:
        _REDIS_CLIENT = redis.from_url(redis_url, decode_responses=True)
        # Check connection
        await _REDIS_CLIENT.ping()
        logger.info(f"Connected to Redis at {redis_url} for BYOK management.")
        
        # Start pubsub listener
        _PUBSUB_TASK = asyncio.create_task(_pubsub_listener())
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e} (BYOK mode disabled)")
        _REDIS_CLIENT = None

async def close_byok_manager():
    """Cleanup Redis connection."""
    if _PUBSUB_TASK:
        _PUBSUB_TASK.cancel()
    if _REDIS_CLIENT:
        await _REDIS_CLIENT.close()

async def _pubsub_listener():
    if not _REDIS_CLIENT:
        return
    try:
        pubsub = _REDIS_CLIENT.pubsub()
        await pubsub.subscribe("channel_update")
        async for message in pubsub.listen():
            if message["type"] == "message":
                user_id = message["data"]
                if user_id in _L1_CACHE:
                    del _L1_CACHE[user_id]
                    logger.info(f"Invalidated L1 cache for user {user_id} due to Pub/Sub message.")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Redis Pub/Sub listener error: {e}")

async def _publish_update(user_id: str):
    """Publish a channel update event to invalidate L1 caches across nodes."""
    if _REDIS_CLIENT:
        await _REDIS_CLIENT.publish("channel_update", user_id)
        # Also clear local cache immediately
        if user_id in _L1_CACHE:
            del _L1_CACHE[user_id]

async def get_user_channels(user_id: str) -> List[Dict]:
    """Get all channels for a user, utilizing L1 cache and Redis."""
    if user_id in _L1_CACHE:
        return _L1_CACHE[user_id]
    
    if not _REDIS_CLIENT:
        return []
    
    try:
        redis_key = f"byok:pool:{user_id}"
        # channels stored as HASH: channel_id -> json string
        channels_raw = await _REDIS_CLIENT.hgetall(redis_key)
        channels = []
        for channel_id, channel_data_str in channels_raw.items():
            try:
                channel_data = json.loads(channel_data_str)
                # Decrypt the token value before returning to memory
                encrypted_val = channel_data.get("value", "")
                decrypted_val = decrypt_token(encrypted_val)
                if decrypted_val:
                    channel_data["value"] = decrypted_val
                    channels.append(channel_data)
            except Exception as e:
                logger.error(f"Error parsing channel {channel_id} for user {user_id}: {e}")
        
        _L1_CACHE[user_id] = channels
        return channels
    except Exception as e:
        logger.error(f"Error fetching channels from Redis for {user_id}: {e}")
        return []

async def add_user_channel(user_id: str, name: str, token_value: str) -> Optional[Dict]:
    """Add a new Tabbit channel for the user, encrypting the token."""
    if not _REDIS_CLIENT:
        return None
    
    channel_id = str(uuid.uuid4())
    encrypted_val = encrypt_token(token_value)
    
    channel_data = {
        "id": channel_id,
        "name": name,
        "value": encrypted_val,
        "status": "active",
        "created_at": time.time(),
        "error_count": 0,
        "total_requests": 0
    }
    
    try:
        redis_key = f"byok:pool:{user_id}"
        await _REDIS_CLIENT.hset(redis_key, channel_id, json.dumps(channel_data))
        await _publish_update(user_id)
        
        # Return decrypted version for API response
        result = channel_data.copy()
        result["value"] = token_value
        return result
    except Exception as e:
        logger.error(f"Error adding channel for {user_id}: {e}")
        return None

async def delete_user_channel(user_id: str, channel_id: str) -> bool:
    """Delete a user channel."""
    if not _REDIS_CLIENT:
        return False
    
    try:
        redis_key = f"byok:pool:{user_id}"
        res = await _REDIS_CLIENT.hdel(redis_key, channel_id)
        if res > 0:
            await _publish_update(user_id)
            return True
        return False
    except Exception as e:
        logger.error(f"Error deleting channel {channel_id} for {user_id}: {e}")
        return False

async def get_assigned_proxy(user_id: str) -> Optional[str]:
    """Get the assigned proxy for the user from Redis."""
    if not _REDIS_CLIENT:
        return None
    try:
        assigned = await _REDIS_CLIENT.hget("byok:proxy_assignments", user_id)
        return assigned
    except Exception as e:
        logger.error(f"Error getting assigned proxy for {user_id}: {e}")
        return None

async def assign_least_loaded_proxy(user_id: str, available_proxies: List[str]) -> Optional[str]:
    """Assign the proxy with the least number of users to this user."""
    if not _REDIS_CLIENT or not available_proxies:
        # Fallback to random or md5 if Redis is not available
        if available_proxies:
            import hashlib
            idx = int(hashlib.md5(user_id.encode()).hexdigest(), 16) % len(available_proxies)
            return available_proxies[idx]
        return None
    try:
        # Check if already assigned
        assigned = await _REDIS_CLIENT.hget("byok:proxy_assignments", user_id)
        if assigned in available_proxies:
            return assigned
            
        # Get counts for all proxies
        counts_raw = await _REDIS_CLIENT.hgetall("byok:proxy_counters")
        counts = {p: int(counts_raw.get(p, 0)) for p in available_proxies}
        
        # Find the proxy with minimum count
        least_loaded_proxy = min(counts.keys(), key=lambda k: counts[k])
        
        # Assign it
        await _REDIS_CLIENT.hset("byok:proxy_assignments", user_id, least_loaded_proxy)
        await _REDIS_CLIENT.hincrby("byok:proxy_counters", least_loaded_proxy, 1)
        
        logger.info(f"[Proxy Load Balancer] Assigned proxy {least_loaded_proxy} to user {user_id} (Current load: {counts[least_loaded_proxy] + 1})")
        return least_loaded_proxy
    except Exception as e:
        logger.error(f"Error assigning least loaded proxy for {user_id}: {e}")
        return None
