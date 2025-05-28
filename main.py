from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any, List
import uvicorn
import requests
import json
import openai
import os
from datetime import datetime
import asyncio
from collections import defaultdict
import time
import re
import msal

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

# Microsoft Graph API configuration
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID")
MICROSOFT_SENDER_EMAIL = os.getenv("MICROSOFT_SENDER_EMAIL")  # The email address to send from

# Microsoft Graph API endpoints
MICROSOFT_AUTHORITY = f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}"
MICROSOFT_SCOPE = ["https://graph.microsoft.com/.default"]
GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"

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

async def get_microsoft_access_token() -> str:
    """
    Get access token for Microsoft Graph API using client credentials flow.
    This is for application-only access (no user interaction required).
    """
    try:
        # Create a confidential client application
        app = msal.ConfidentialClientApplication(
            MICROSOFT_CLIENT_ID,
            authority=MICROSOFT_AUTHORITY,
            client_credential=MICROSOFT_CLIENT_SECRET,
        )
        
        # Acquire token for client credentials flow
        result = app.acquire_token_for_client(scopes=MICROSOFT_SCOPE)
        
        if "access_token" in result:
            return result["access_token"]
        else:
            error_msg = f"Failed to acquire access token: {result.get('error_description', 'Unknown error')}"
            print(error_msg)
            raise Exception(error_msg)
            
    except Exception as e:
        error_msg = f"Error getting Microsoft access token: {str(e)}"
        print(error_msg)
        raise Exception(error_msg)

async def send_email_via_outlook(
    to_email: str,
    subject: str,
    body: str,
    cc_emails: Optional[List[str]] = None,
    bcc_emails: Optional[List[str]] = None,
    is_html: bool = True
) -> dict:
    """
    Send email via Microsoft Graph API (Outlook).
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body content
        cc_emails: List of CC email addresses (optional)
        bcc_emails: List of BCC email addresses (optional)
        is_html: Whether body is HTML (default: True)
    
    Returns:
        dict: Response with success status and details
    """
    try:
        # Get access token
        access_token = await get_microsoft_access_token()
        
        # Prepare recipients
        recipients = [{"emailAddress": {"address": to_email}}]
        
        cc_recipients = []
        if cc_emails:
            cc_recipients = [{"emailAddress": {"address": email}} for email in cc_emails]
        
        bcc_recipients = []
        if bcc_emails:
            bcc_recipients = [{"emailAddress": {"address": email}} for email in bcc_emails]
        
        # Prepare email message
        email_message = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML" if is_html else "Text",
                    "content": body
                },
                "toRecipients": recipients
            }
        }
        
        # Add CC recipients if provided
        if cc_recipients:
            email_message["message"]["ccRecipients"] = cc_recipients
            
        # Add BCC recipients if provided
        if bcc_recipients:
            email_message["message"]["bccRecipients"] = bcc_recipients
        
        print(f"Sending email to {to_email} with subject: {subject}")
        
        # Send email via Microsoft Graph API
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Use the sender's mailbox endpoint
        send_url = f"{GRAPH_API_ENDPOINT}/users/{MICROSOFT_SENDER_EMAIL}/sendMail"
        
        response = requests.post(
            send_url,
            headers=headers,
            json=email_message,
            timeout=30
        )
        
        if response.status_code == 202:  # Microsoft Graph returns 202 for successful email send
            print("Email sent successfully via Outlook")
            return {
                "success": True,
                "message": "Email sent successfully",
                "response_code": response.status_code,
                "timestamp": datetime.now().isoformat()
            }
        else:
            error_msg = f"Microsoft Graph API returned {response.status_code}: {response.text}"
            print(f"Email send error: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "response_code": response.status_code,
                "response_text": response.text,
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        error_msg = f"Error sending email via Outlook: {str(e)}"
        print(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        }

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

def parse_error_code_from_content(content: str) -> int:
    """
    Parse error code from webhook response content.
    Looks for patterns like [400], [500], etc.
    Returns the parsed code or None if not found.
    """
    if not content:
        return None
    
    # Look for pattern like [400], [500], etc.
    match = re.search(r'\[(\d{3})\]', content)
    if match:
        return int(match.group(1))
    
    return None

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
            # Parse error code from response content
            parsed_error_code = parse_error_code_from_content(response.text)
            effective_status_code = parsed_error_code or response.status_code
            
            error_msg = f"Webhook failed with status code: {response.status_code}"
            if parsed_error_code:
                error_msg += f" (parsed error code: {parsed_error_code})"
            
            print(f"{error_msg}")
            print(f"Webhook error response: {response.text}")
            print(f"Response headers: {dict(response.headers)}")
            
            # Only send SMS alerts for 5xx errors (server errors)
            if effective_status_code >= 500:
                await send_error_alert(
                    f"Webhook server error {effective_status_code}. Response: {response.text[:200]}...",
                    "/submit-lead"
                )
            
            return {
                'success': False,
                'response': response_details,
                'parsed_error_code': parsed_error_code,
                'effective_status_code': effective_status_code,
                'message': f'Webhook failed with status {effective_status_code}'
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

# ----- NEW EMAIL ENDPOINT -----

@app.post("/send-email")
async def send_email(
    request: Request,
    to_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    cc_emails: Optional[str] = Form(None),  # Comma-separated string
    bcc_emails: Optional[str] = Form(None),  # Comma-separated string
    is_html: bool = Form(True)
):
    """
    Send email via Microsoft Outlook using Graph API.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body content
        cc_emails: Comma-separated CC email addresses (optional)
        bcc_emails: Comma-separated BCC email addresses (optional)
        is_html: Whether body is HTML (default: True)
    """
    client_ip = request.client.host
    
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    try:
        # Validate required Microsoft Graph configuration
        if not all([MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT_ID, MICROSOFT_SENDER_EMAIL]):
            raise HTTPException(
                status_code=500, 
                detail="Microsoft Graph API configuration missing. Please set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT_ID, and MICROSOFT_SENDER_EMAIL environment variables."
            )
        
        # Parse CC and BCC email lists
        cc_list = []
        if cc_emails:
            cc_list = [email.strip() for email in cc_emails.split(',') if email.strip()]
        
        bcc_list = []
        if bcc_emails:
            bcc_list = [email.strip() for email in bcc_emails.split(',') if email.strip()]
        
        print(f"Sending email to: {to_email}, Subject: {subject}")
        if cc_list:
            print(f"CC: {cc_list}")
        if bcc_list:
            print(f"BCC: {bcc_list}")
        
        # Send email via Microsoft Graph API
        result = await send_email_via_outlook(
            to_email=to_email,
            subject=subject,
            body=body,
            cc_emails=cc_list if cc_list else None,
            bcc_emails=bcc_list if bcc_list else None,
            is_html=is_html
        )
        
        if result['success']:
            return {
                "status": "success",
                "message": "Email sent successfully via Outlook",
                "details": result,
                "timestamp": datetime.now().isoformat()
            }
        else:
            # Send error alert for email failures
            await send_error_alert(f"Email send failed: {result.get('error', 'Unknown error')}", "/send-email")
            
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Failed to send email",
                    "error": result.get('error', 'Unknown error'),
                    "details": result
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Unexpected error sending email: {str(e)}"
        print(error_msg)
        await send_error_alert(error_msg, "/send-email")
        raise HTTPException(status_code=500, detail="Internal server error")

# ----- EXISTING CHATBOT ENDPOINTS -----

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
            
            # Use the effective status code (parsed from content if available)
            effective_status_code = webhook_result.get('effective_status_code', 500)
            
            # Include webhook response details in error
            raise HTTPException(
                status_code=effective_status_code, 
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

@app.post("/test-email")
async def test_email_endpoint(request: Request):
    """
    Test endpoint to verify email functionality with a simple test email.
    """
    client_ip = request.client.host
    
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    try:
        # Validate Microsoft Graph configuration
        if not all([MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT_ID, MICROSOFT_SENDER_EMAIL]):
            raise HTTPException(
                status_code=500,
                detail="Microsoft Graph API configuration missing"
            )
        
        # Send a test email
        test_subject = "Test Email from Law Firm Chatbot API"
        test_body = f"""
        <html>
        <body>
            <h2>Test Email</h2>
            <p>This is a test email sent from the Law Firm Chatbot API at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.</p>
            <p>If you received this email, the Microsoft Outlook integration is working correctly.</p>
        </body>
        </html>
        """
        
        result = await send_email_via_outlook(
            to_email=MICROSOFT_SENDER_EMAIL,  # Send to self for testing
            subject=test_subject,
            body=test_body,
            is_html=True
        )
        
        if result['success']:
            return {
                "status": "success",
                "message": "Test email sent successfully",
                "details": result,
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Failed to send test email",
                    "error": result.get('error', 'Unknown error'),
                    "details": result
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error in test email endpoint: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

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

    # Microsoft Graph API variables (optional but recommended)
    microsoft_env_vars = [
        "MICROSOFT_CLIENT_ID",
        "MICROSOFT_CLIENT_SECRET",
        "MICROSOFT_TENANT_ID",
        "MICROSOFT_SENDER_EMAIL"
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        print(f"WARNING: Missing required environment variables: {', '.join(missing_vars)}")

    missing_microsoft_vars = [var for var in microsoft_env_vars if not os.getenv(var)]
    if missing_microsoft_vars:
        print(f"WARNING: Missing Microsoft Graph API environment variables: {', '.join(missing_microsoft_vars)}")
        print("Email functionality will not work without these variables.")

    uvicorn.run(app, host="0.0.0.0", port=10000)