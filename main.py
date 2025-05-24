from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
import uvicorn
import requests
import json
import openai
import os
from datetime import datetime
import asyncio
from collections import defaultdict
import time

app = FastAPI()

# Add CORS middleware to allow requests from your website
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domain
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Configure OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

# Environment variables for API keys
DOCSBOT_TEAM_ID = os.getenv("DOCSBOT_TEAM_ID")
DOCSBOT_BOT_ID = os.getenv("DOCSBOT_BOT_ID") 
DOCSBOT_API_KEY = os.getenv("DOCSBOT_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "+19133956075")
TWILIO_TO_NUMBER = os.getenv("TWILIO_TO_NUMBER", "+19134753876")
ALERT_PHONE_NUMBER = "+19136020456"  # Your phone number for alerts

# Webhook URL
MAKE_WEBHOOK_URL = "https://hook.us2.make.com/ws7b3t1c2p6xnp7s0gd9zr2yr7rlitam"

# Rate limiting storage (in production, use Redis)
rate_limit_storage = defaultdict(list)
RATE_LIMIT_REQUESTS = 100  # requests per window
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds

def check_rate_limit(client_ip: str) -> bool:
    """Simple rate limiting check"""
    now = time.time()
    # Clean old requests
    rate_limit_storage[client_ip] = [
        req_time for req_time in rate_limit_storage[client_ip] 
        if now - req_time < RATE_LIMIT_WINDOW
    ]
    
    # Check if under limit
    if len(rate_limit_storage[client_ip]) >= RATE_LIMIT_REQUESTS:
        return False
    
    # Add current request
    rate_limit_storage[client_ip].append(now)
    return True

async def send_error_alert(error_message: str, endpoint: str):
    """Send SMS alert when API errors occur"""
    try:
        alert_message = f"Roth Davies Chatbot Error Alert: {error_message} at endpoint {endpoint}. Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Send SMS to alert phone number
        response = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            data={
                'To': ALERT_PHONE_NUMBER,
                'From': TWILIO_FROM_NUMBER,
                'Body': alert_message
            },
            timeout=10
        )
        
        if response.status_code == 201:
            print(f"Error alert sent successfully for {endpoint}")
        else:
            print(f"Failed to send error alert: {response.status_code}")
            
    except Exception as e:
        print(f"Failed to send error alert: {e}")

def get_spam_detection_prompt(name: str, phone: str, email: str, about_case: str) -> str:
    """
    Comprehensive prompt for spam detection tailored to a law firm context.
    """
    return f"""You are an expert spam detection system for a law firm specializing in personal injury, criminal law, and divorce law. Your job is to analyze incoming form submissions and determine if they are legitimate potential client inquiries or spam.

FIRM CONTEXT:
- Personal injury law (car accidents, slip and fall, medical malpractice, workplace injuries)
- Criminal law (DUI, drug charges, assault, theft, domestic violence, traffic violations)
- Divorce law (divorce proceedings, custody disputes, alimony, property division)

ANALYZE THIS SUBMISSION:
Name: "{name}"
Phone: "{phone}" 
Email: "{email}"
Case Description: "{about_case}"

SPAM INDICATORS TO CHECK FOR:
1. **Irrelevant Services**: Mentions of SEO, marketing, web design, crypto, investments, business loans, insurance sales, etc.
2. **Generic Templates**: Obviously copy-pasted text, excessive keywords, unnatural language patterns
3. **Fake Personal Info**: Obviously fake names (like "Test User", nonsensical names), invalid phone formats, suspicious email patterns
4. **Promotional Content**: Trying to sell products/services, offering business opportunities, affiliate marketing
5. **Technical Spam**: URLs, suspicious links, HTML tags, excessive special characters
6. **Off-topic Inquiries**: Requests completely unrelated to legal services (tech support, medical advice, etc.)
7. **Automated Messages**: Clearly bot-generated content, repetitive phrases, unnatural sentence structure
8. **Gibberish**: Random characters, nonsensical text, foreign spam content

LEGITIMATE INDICATORS:
1. **Relevant Legal Issues**: Mentions accidents, injuries, arrests, charges, divorce, custody, legal problems
2. **Personal Details**: Specific circumstances, dates, locations, genuine concern/urgency
3. **Natural Language**: Human-like writing style, emotional context, personal pronouns
4. **Valid Contact Info**: Realistic names, properly formatted phone numbers, legitimate email addresses
5. **Specific Requests**: Asking for consultation, legal advice, representation, case evaluation

DECISION CRITERIA:
- If submission contains ANY clear spam indicators and NO legitimate legal context → SPAM
- If submission is about legitimate legal matters with reasonable contact info → NOT SPAM
- If submission is borderline but shows genuine legal need → NOT SPAM (err on side of caution)
- If submission is clearly trying to sell something or is completely off-topic → SPAM

IMPORTANT NOTES:
- Be conservative - it's better to let through a borderline case than reject a real client
- Focus on the case description content more than contact info formatting
- Consider that real people may have typos, brief descriptions, or unusual circumstances

Respond with ONLY one word: "SPAM" or "LEGITIMATE"

Examples:
- "I was in a car accident last week and need help" → LEGITIMATE
- "We offer SEO services to grow your law firm" → SPAM  
- "My husband filed for divorce, need attorney" → LEGITIMATE
- "Make money from home with crypto trading" → SPAM
- "Got arrested for DUI last night" → LEGITIMATE
- Random gibberish or foreign spam → SPAM

Your response (one word only):"""

async def check_for_spam(name: str, phone: str, email: str, about_case: str) -> bool:
    """
    Use GPT-4o-mini to determine if the submission is spam.
    Returns True if spam, False if legitimate.
    """
    try:
        prompt = get_spam_detection_prompt(name, phone, email, about_case)
        
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a spam detection expert for a law firm. Respond with only 'SPAM' or 'LEGITIMATE'."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            max_tokens=10,
            temperature=0.1  # Low temperature for consistent results
        )
        
        result = response.choices[0].message.content.strip().upper()
        print(f"Spam detection result: {result}")
        
        # Log the analysis for monitoring
        print(f"Analyzed submission - Name: {name}, Email: {email}, Result: {result}")
        
        return result == "SPAM"
        
    except Exception as e:
        print(f"Error in spam detection: {e}")
        await send_error_alert(f"OpenAI spam detection failed: {str(e)}", "/submit-lead")
        # If OpenAI fails, err on the side of caution and allow the submission
        print("Spam detection failed, allowing submission through")
        return False

async def send_to_webhook(name: str, phone: str, email: str, about_case: str) -> dict:
    """
    Send the legitimate submission to the webhook.
    Returns dict with success status and response details.
    """
    try:
        # Prepare the form data
        form_data = {
            'name': name,
            'phone': phone,
            'email': email,
            'about_case': about_case
        }
        
        print(f"Sending to webhook: {form_data}")
        
        # Send POST request to make.com webhook
        response = requests.post(
            MAKE_WEBHOOK_URL,
            data=form_data,
            timeout=30
        )
        
        # Capture response details
        response_details = {
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'content': response.text,
            'url': response.url,
            'elapsed_seconds': response.elapsed.total_seconds()
        }
        
        if response.status_code == 200:
            print("Successfully sent to webhook")
            print(f"Webhook response: Status={response.status_code}, Content={response.text}")
            
            return {
                'success': True,
                'response': response_details,
                'message': 'Successfully sent to webhook'
            }
        else:
            error_msg = f"Webhook failed with status code: {response.status_code}"
            print(f"{error_msg}")
            print(f"Webhook error response: {response.text}")
            print(f"Response headers: {dict(response.headers)}")
            
            # Send detailed error alert including response content
            await send_error_alert(
                f"Webhook failed with status {response.status_code}. Response: {response.text[:200]}...",
                "/submit-lead"
            )
            
            return {
                'success': False,
                'response': response_details,
                'message': f'Webhook failed with status {response.status_code}'
            }
            
    except requests.exceptions.Timeout as e:
        error_msg = f"Webhook request timed out: {str(e)}"
        print(error_msg)
        await send_error_alert(f"Webhook timeout: {str(e)}", "/submit-lead")
        
        return {
            'success': False,
            'response': {'error': 'timeout', 'details': str(e)},
            'message': 'Webhook request timed out'
        }
        
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Webhook connection error: {str(e)}"
        print(error_msg)
        await send_error_alert(f"Webhook connection failed: {str(e)}", "/submit-lead")
        
        return {
            'success': False,
            'response': {'error': 'connection_error', 'details': str(e)},
            'message': 'Failed to connect to webhook'
        }
        
    except Exception as e:
        error_msg = f"Unexpected error sending to webhook: {str(e)}"
        print(error_msg)
        await send_error_alert(f"Webhook request failed: {str(e)}", "/submit-lead")
        
        return {
            'success': False,
            'response': {'error': 'unexpected_error', 'details': str(e)},
            'message': 'Unexpected error occurred'
        }

# ----- NEW CHATBOT ENDPOINTS -----

@app.post("/warm")
async def warm_server(request: Request):
    """Simple warming endpoint to keep the server alive"""
    client_ip = request.client.host
    
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    return {
        "status": "warm",
        "timestamp": datetime.now().isoformat(),
        "message": "Server is alive and ready"
    }

@app.post("/chat-docsbot")
async def chat_with_docsbot(
    request: Request,
    conversation_id: str = Form(...),
    question: str = Form(...),
    conversation_history: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    context_items: int = Form(3),
    full_source: bool = Form(True)
):
    """Handle DocsBots chat API requests"""
    client_ip = request.client.host
    
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    try:
        # Parse JSON strings if provided
        parsed_history = json.loads(conversation_history) if conversation_history else []
        parsed_metadata = json.loads(metadata) if metadata else {}
        
        # Prepare request body for DocsBots
        request_body = {
            "conversationId": conversation_id,
            "question": question,
            "conversation_history": parsed_history,
            "metadata": parsed_metadata,
            "context_items": context_items,
            "human_escalation": False,
            "followup_rating": False,
            "document_retriever": True,
            "full_source": full_source,
            "stream": False
        }
        
        print(f"Sending to DocsBots API: {json.dumps(request_body, indent=2)}")
        
        # Make request to DocsBots API
        response = requests.post(
            f"https://api.docsbot.ai/teams/{DOCSBOT_TEAM_ID}/bots/{DOCSBOT_BOT_ID}/chat-agent",
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {DOCSBOT_API_KEY}'
            },
            json=request_body,
            timeout=30
        )
        
        if not response.ok:
            error_msg = f"DocsBots API returned {response.status_code}"
            print(f"DocsBots API error: {error_msg}")
            await send_error_alert(error_msg, "/chat-docsbot")
            raise HTTPException(status_code=response.status_code, detail=error_msg)
        
        response_data = response.json()
        print(f"DocsBots response: {json.dumps(response_data, indent=2)}")
        
        return {
            "status": "success",
            "data": response_data,
            "timestamp": datetime.now().isoformat()
        }
        
    except requests.exceptions.RequestException as e:
        error_msg = f"DocsBots API request failed: {str(e)}"
        print(error_msg)
        await send_error_alert(error_msg, "/chat-docsbot")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in request parameters: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Unexpected error in chat endpoint: {str(e)}"
        print(error_msg)
        await send_error_alert(error_msg, "/chat-docsbot")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/get-resources")
async def get_resources_for_case(
    request: Request,
    conversation_id: str = Form(...),
    question: str = Form(...),
    metadata: Optional[str] = Form(None),
    context_items: int = Form(5)
):
    """Get resources from DocsBots for case description"""
    client_ip = request.client.host
    
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    try:
        # Parse metadata if provided
        parsed_metadata = json.loads(metadata) if metadata else {}
        
        # Prepare request body for DocsBots
        request_body = {
            "conversationId": conversation_id,
            "question": question,
            "metadata": parsed_metadata,
            "context_items": context_items,
            "human_escalation": False,
            "followup_rating": False,
            "document_retriever": True,
            "full_source": True,
            "stream": False
        }
        
        print(f"Getting resources from DocsBots: {json.dumps(request_body, indent=2)}")
        
        # Make request to DocsBots API
        response = requests.post(
            f"https://api.docsbot.ai/teams/{DOCSBOT_TEAM_ID}/bots/{DOCSBOT_BOT_ID}/chat-agent",
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {DOCSBOT_API_KEY}'
            },
            json=request_body,
            timeout=30
        )
        
        if not response.ok:
            error_msg = f"DocsBots API returned {response.status_code}"
            print(f"DocsBots API error: {error_msg}")
            await send_error_alert(error_msg, "/get-resources")
            raise HTTPException(status_code=response.status_code, detail=error_msg)
        
        response_data = response.json()
        
        return {
            "status": "success",
            "data": response_data,
            "timestamp": datetime.now().isoformat()
        }
        
    except requests.exceptions.RequestException as e:
        error_msg = f"DocsBots API request failed: {str(e)}"
        print(error_msg)
        await send_error_alert(error_msg, "/get-resources")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in metadata: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Unexpected error in resources endpoint: {str(e)}"
        print(error_msg)
        await send_error_alert(error_msg, "/get-resources")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/send-sms")
async def send_sms_notification(
    request: Request,
    phone_number: str = Form(...),
    user_name: str = Form(...),
    case_type: str = Form(...),
    location: str = Form(...),
    is_referral: bool = Form(False)
):
    """Send SMS notification via Twilio"""
    client_ip = request.client.host
    
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    try:
        # Format the message
        message_body = f"Roth Davies Chatbot - New Incoming Client: {user_name} - {case_type} case in {location}. Phone: {phone_number}"
        if is_referral:
            message_body += " (Referral Request)"
        
        print(f"Sending SMS: {message_body}")
        
        # Send SMS via Twilio
        response = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            data={
                'To': TWILIO_TO_NUMBER,
                'From': TWILIO_FROM_NUMBER,
                'Body': message_body
            },
            timeout=15
        )
        
        if response.status_code == 201:
            print("SMS sent successfully")
            return {
                "status": "success",
                "message": "SMS sent successfully",
                "timestamp": datetime.now().isoformat()
            }
        else:
            error_msg = f"Twilio API returned {response.status_code}"
            print(f"Twilio error: {error_msg}, Response: {response.text}")
            await send_error_alert(error_msg, "/send-sms")
            raise HTTPException(status_code=response.status_code, detail=error_msg)
            
    except requests.exceptions.RequestException as e:
        error_msg = f"Twilio API request failed: {str(e)}"
        print(error_msg)
        await send_error_alert(error_msg, "/send-sms")
        raise HTTPException(status_code=503, detail="SMS service temporarily unavailable")
    except Exception as e:
        error_msg = f"Unexpected error in SMS endpoint: {str(e)}"
        print(error_msg)
        await send_error_alert(error_msg, "/send-sms")
        raise HTTPException(status_code=500, detail="Internal server error")

# ----- EXISTING ENDPOINTS -----

@app.post("/submit-lead")
async def submit_lead(
    request: Request,
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    email: str = Form(...),
    about_case: str = Form(...)
):
    """
    Main endpoint that filters spam and forwards legitimate submissions to webhook.
    """
    client_ip = request.client.host
    
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    try:
        print(f"Received submission from {name} ({email})")
        
        # Basic validation
        if not name or not email or not about_case:
            raise HTTPException(status_code=400, detail="Missing required fields: name, email, and about_case are required")
        
        # Check for spam using GPT-4o-mini
        is_spam = await check_for_spam(name, phone or "", email, about_case)
        
        if is_spam:
            print(f"Submission from {name} ({email}) detected as SPAM - rejected")
            return {
                "status": "rejected",
                "reason": "Submission detected as spam",
                "timestamp": datetime.now().isoformat()
            }
        
        # Send legitimate submission to webhook and get detailed response
        webhook_result = await send_to_webhook(name, phone or "", email, about_case)
        
        if webhook_result['success']:
            print(f"Submission from {name} ({email}) successfully processed and forwarded")
            
            # Return success with webhook response details
            return {
                "status": "success",
                "message": "Lead submitted successfully",
                "webhook_response": webhook_result['response'],
                "timestamp": datetime.now().isoformat()
            }
        else:
            print(f"Failed to forward submission from {name} ({email}) to webhook")
            print(f"Webhook failure details: {webhook_result}")
            
            # Include webhook response details in error
            raise HTTPException(
                status_code=500, 
                detail={
                    "message": "Failed to process submission",
                    "webhook_error": webhook_result
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error processing submission: {e}")
        await send_error_alert(f"Lead submission error: {str(e)}", "/submit-lead")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Law Firm Chatbot API"
    }

@app.post("/test-spam-detection")
async def test_spam_detection(
    request: Request,
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    email: str = Form(...),
    about_case: str = Form(...)
):
    """
    Test endpoint to check spam detection without sending to webhook.
    """
    client_ip = request.client.host
    
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    try:
        is_spam = await check_for_spam(name, phone or "", email, about_case)
        
        return {
            "name": name,
            "email": email,
            "is_spam": is_spam,
            "result": "SPAM" if is_spam else "LEGITIMATE",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"Error in spam detection test: {e}")
        raise HTTPException(status_code=500, detail="Spam detection test failed")

if __name__ == "__main__":
    # Check for required environment variables
    required_env_vars = [
        "OPENAI_API_KEY",
        "DOCSBOT_TEAM_ID", 
        "DOCSBOT_BOT_ID",
        "DOCSBOT_API_KEY",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN"
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        print(f"WARNING: Missing environment variables: {', '.join(missing_vars)}")
    
    uvicorn.run(app, host="0.0.0.0", port=10000)