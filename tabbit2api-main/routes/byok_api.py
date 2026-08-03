from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
import core.byok_manager as byok

router = APIRouter()

class AddChannelRequest(BaseModel):
    name: str
    token_value: str

def get_user_id(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    
    # Also support x-api-key for Claude compatible requests
    api_key = request.headers.get("x-api-key", "")
    if api_key:
        return api_key
        
    raise HTTPException(
        status_code=401, 
        detail={
            "error": {
                "message": "Missing API Key. Please provide it via 'Authorization: Bearer <sk-...>' or 'x-api-key'.",
                "type": "invalid_request_error",
                "code": "missing_api_key"
            }
        }
    )

@router.get("/v1/byok/channels")
async def list_channels(user_id: str = Depends(get_user_id)):
    channels = await byok.get_user_channels(user_id)
    # mask tokens
    res = []
    for c in channels:
        cc = c.copy()
        v = cc.get("value", "")
        if len(v) > 10:
            cc["value"] = v[:4] + "***" + v[-4:]
        else:
            cc["value"] = "***"
        res.append(cc)
    return {"data": res}

@router.post("/v1/byok/channels")
async def add_channel(req: AddChannelRequest, user_id: str = Depends(get_user_id)):
    if not req.token_value:
        raise HTTPException(status_code=400, detail="token_value is required")
    
    res = await byok.add_user_channel(user_id, req.name, req.token_value)
    if not res:
        raise HTTPException(status_code=500, detail="Failed to add channel (Redis offline or error)")
    
    # Mask it in response
    v = res["value"]
    if len(v) > 10:
        res["value"] = v[:4] + "***" + v[-4:]
    return res

@router.delete("/v1/byok/channels/{channel_id}")
async def delete_channel(channel_id: str, user_id: str = Depends(get_user_id)):
    success = await byok.delete_user_channel(user_id, channel_id)
    if not success:
        raise HTTPException(status_code=404, detail="Channel not found or already deleted")
    return {"status": "ok"}
