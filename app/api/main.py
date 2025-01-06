from fastapi import FastAPI, Request
import httpx
from app.ai.chat_ai_call_wa import chat_with_ai
from app.utils.messaging import send_whatsapp_message, send_whatsapp_response

app = FastAPI()

# Global dictionary to store conversation history per user
conversation_history = {}  # Declare this at the module level


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Handle incoming WhatsApp messages from WHAPI and respond using AI.
    """
    global conversation_history

    try:

        # Parse the incoming JSON payload from WHAPI
        body = await request.json()

        # Check the event type
        event_type = body.get('event', {}).get('type', '')

        if event_type == "messages":
            message_data = body.get("messages")[0]
            if not message_data["from_me"]:
                chat_id_address = message_data["chat_id"]
                chat_id, chat_type = chat_id_parsor(chat_id_address)
                user_id = message_data["from"]  # WhatsApp user ID
                if message_data.get("type", '') == "text":
                    user_message = message_data.get("text", {}).get("body", "").strip()

                    # Retrieve or initialize conversation history for this user
                    if user_id not in conversation_history:
                        conversation_history[user_id] = []

                    # Interact with the AI
                    if user_message:
                        ai_response = await chat_with_ai(user_message, user_id, messages=conversation_history[user_id])
                        # Save the updated conversation history
                        conversation_history[user_id] = ai_response  # This includes the entire chat so far
                        # Send the response back to the user via WHAPI
                        async with httpx.AsyncClient() as client:
                            recipient_id = (
                                chat_id + "@g.us" if chat_type == "g.us"
                                else user_id + "@s.whatsapp.net"
                            )
                            await send_whatsapp_response(client, recipient_id, ai_response)

                if message_data.get("type", '') == "voice":
                    user_voice_message = message_data.get("voice", {}).get("link", "").strip()

                    # Retrieve or initialize conversation history for this user
                    if user_id not in conversation_history:
                        conversation_history[user_id] = []

                    # Interact with the AI
                    if user_voice_message:
                        # download the audio message
                        # convert with ffmpeg in mp3
                        # transcription of the audio with openai-whisper
                        # send to Helpy
                        ai_response = await chat_with_ai(user_voice_message, user_id, messages=conversation_history[user_id])
                        # Save the updated conversation history
                        conversation_history[user_id] = ai_response  # This includes the entire chat so far
                        # Send the response back to the user via WHAPI
                        async with httpx.AsyncClient() as client:
                            recipient_id = user_id
                            await send_whatsapp_message(client, recipient_id, ai_response[-1]["content"])

        elif event_type == 'statuses':
            # Handle status updates (read receipts, etc.)
            print(f"Status event received: {body['statuses']}")

        else:
            print(f"Unknown event type: {event_type}")

        return {"success": True}

    except Exception as e:
        print(f"Error in whatsapp_webhook: {e}")
        return {"status": "error", "reason": str(e)}


@app.post("/webhook/sms")
async def sms_webhook(request: Request):
    """
    Handle incoming SMS messages from operator and respond using AI.
    """
    global conversation_history

    try:

        # Parse the incoming JSON payload from SMS
        body = await request.json()

        # Check the event type
        event_type = body.get('event', {}).get('type', '')

        if event_type == "sms":
            message_data = body.get("sms")[0]
            user_id = message_data["from"]  # WhatsApp user ID
            user_message = message_data.get("text", {}).get("body", "").strip()

            # Retrieve or initialize conversation history for this user
            if user_id not in conversation_history:
                conversation_history[user_id] = []

            # Interact with the AI
            if user_message:
                ai_response = await chat_with_ai(user_message, user_id, messages=conversation_history[user_id])
                # Save the updated conversation history
                conversation_history[user_id] = ai_response  # This includes the entire chat so far
                # Send the response back to the user via WHAPI
                async with httpx.AsyncClient() as client:
                    recipient_id = user_id
                    # send to endpoint of Annatel
                    # await send_sms_message(client, recipient_id, ai_response[-1]["content"])

        elif event_type == 'statuses':
            # Handle status updates (read receipts, etc.)
            print(f"Status event received: {body['statuses']}")

        else:
            print(f"Unknown event type: {event_type}")

        return {"success": True}

    except Exception as e:
        print(f"Error in whatsapp_webhook: {e}")
        return {"status": "error", "reason": str(e)}


def chat_id_parsor (chat_id: str):
    chat_id_splitted = chat_id.split("@")
    return chat_id_splitted
