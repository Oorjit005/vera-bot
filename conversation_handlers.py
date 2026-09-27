import asyncio

from app.reply.respond import respond


def respond_sync(state: dict, merchant_message: str) -> dict:
    body = {
        "conversation_id": state.get("conversation_id", ""),
        "merchant_id": state.get("merchant_id"),
        "customer_id": state.get("customer_id"),
        "from_role": state.get("from_role", "merchant"),
        "message": merchant_message,
        "received_at": state.get("received_at", ""),
        "turn_number": state.get("turn_number", 1),
    }
    return asyncio.run(respond(body))


__all__ = ["respond_sync"]
