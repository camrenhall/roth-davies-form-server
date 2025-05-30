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
from mailersend import emails

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
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")
TWILIO_TO_NUMBER = os.getenv("TWILIO_TO_NUMBER")
ALERT_PHONE_NUMBER = os.getenv("ALERT_PHONE_NUMBER")

# MailerSend configuration
MAILERSEND_API_KEY = os.getenv("MAILERSEND_API_KEY")
MAILERSEND_FROM_EMAIL = os.getenv("MAILERSEND_FROM_EMAIL")
MAILERSEND_FROM_NAME = os.getenv("MAILERSEND_FROM_NAME")
FIRM_NOTIFICATION_EMAIL = os.getenv("FIRM_NOTIFICATION_EMAIL")

# Template IDs for different channels
FORM_TEMPLATE_ID = os.getenv("FORM_TEMPLATE_ID")
CHATBOT_TEMPLATE_ID = os.getenv("CHATBOT_TEMPLATE_ID")

# Webhook URL
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")

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

async def send_email_via_mailersend(
    to_email: str,
    to_name: str = "",
    template_id: Optional[str] = None,
    subject: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
    html_content: Optional[str] = None,
    text_content: Optional[str] = None,
    from_name: Optional[str] = None
) -> dict:
    """
    Send email via MailerSend API with template support and variable injection.
    """
    try:
        if not MAILERSEND_API_KEY:
            raise Exception("MAILERSEND_API_KEY not configured")
        
        # Initialize MailerSend client
        mailer = emails.NewEmail(MAILERSEND_API_KEY)
        
        # Create mail body dict
        mail_body = {}
        
        # Set sender information
        sender_name = from_name or MAILERSEND_FROM_NAME
        mail_from = {
            "name": sender_name,
            "email": MAILERSEND_FROM_EMAIL,
        }
        
        # Set recipient information
        recipients = [
            {
                "name": to_name,
                "email": to_email,
            }
        ]
        
        # Set sender and recipient
        mailer.set_mail_from(mail_from, mail_body)
        mailer.set_mail_to(recipients, mail_body)
        
        # Use template or direct content
        if template_id:
            # Using template with variables
            mailer.set_template(template_id, mail_body)
            
            # Set subject if provided (otherwise template subject is used)
            if subject:
                mailer.set_subject(subject, mail_body)
            
            # Set personalization variables if provided
            if variables:
                # Format variables for MailerSend personalization
                personalization = [
                    {
                        "email": to_email,
                        "data": variables
                    }
                ]
                mailer.set_personalization(personalization, mail_body)
                
        else:
            # Using direct content (no template)
            if not subject:
                raise Exception("Subject is required when not using a template")
            
            mailer.set_subject(subject, mail_body)
            
            if html_content:
                mailer.set_html_content(html_content, mail_body)
            
            if text_content:
                mailer.set_plaintext_content(text_content, mail_body)
            
            if not html_content and not text_content:
                raise Exception("Either html_content or text_content is required when not using a template")
        
        print(f"Sending email via MailerSend to: {to_email}, Name: {to_name}")
        if variables:
            print(f"Template variables: {variables}")
        
        # Send the email
        response = mailer.send(mail_body)
        
        if hasattr(response, 'status_code') and response.status_code == 202:
            print("Email sent successfully via MailerSend")
            return {
                "success": True,
                "message": "Email sent successfully",
                "status_code": response.status_code,
                "response_data": response.json() if hasattr(response, 'json') else None,
                "timestamp": datetime.now().isoformat()
            }
        else:
            error_msg = f"MailerSend API returned unexpected response: {response}"
            print(f"Email send error: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "status_code": getattr(response, 'status_code', 'unknown'),
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        error_msg = f"Error sending email via MailerSend: {str(e)}"
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

async def send_to_webhook(webhook_data: dict) -> dict:
    """
    Send the submission data to the webhook in a unified format.
    Returns dict with success status and response details.
    """
    try:
        print(f"Sending to webhook: {webhook_data}")
        
        # Send POST request to make.com webhook
        response = requests.post(
            MAKE_WEBHOOK_URL,
            data=webhook_data,
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

async def send_sms_notification(phone_number: str, user_name: str, source: str, case_info: str, is_referral: bool = False):
    """Send SMS notification via Twilio"""
    try:
        # Format the message based on source
        if source == "form":
            message_body = f"Roth Davies Form - New Lead: {user_name} - {case_info}. Phone: {phone_number}"
        else:  # chatbot
            message_body = f"Roth Davies Chatbot - New Lead: {user_name} - {case_info}. Phone: {phone_number}"
        
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
            return True
        else:
            error_msg = f"Twilio API returned {response.status_code}"
            print(f"Twilio error: {error_msg}, Response: {response.text}")
            await send_error_alert(error_msg, "/submit-lead")
            return False
            
    except requests.exceptions.RequestException as e:
        error_msg = f"Twilio API request failed: {str(e)}"
        print(error_msg)
        await send_error_alert(error_msg, "/submit-lead")
        return False
    except Exception as e:
        error_msg = f"Unexpected error in SMS: {str(e)}"
        print(error_msg)
        await send_error_alert(error_msg, "/submit-lead")
        return False

# ----- CONSOLIDATED LEAD SUBMISSION ENDPOINT -----

@app.post("/submit-lead")
async def submit_lead(
    request: Request,
    source: str = Form(...),  # "form" or "chatbot"
    name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    # Form-specific fields
    about_case: Optional[str] = Form(None),  # Form case description
    # Chatbot-specific fields
    case_type: Optional[str] = Form(None),  # Chatbot case type
    case_state: Optional[str] = Form(None),  # Chatbot case state/location
    # Optional fields
    is_referral: bool = Form(False)
):
    """
    Consolidated endpoint that handles both form and chatbot lead submissions.
    
    Args:
        source: Either "form" or "chatbot" to determine processing flow
        name: Lead's name (required for both)
        email: Lead's email (required for both)
        phone: Lead's phone number (optional)
        about_case: Case description (form only)
        case_type: Case type (chatbot only)
        case_state: Case state/location (chatbot only)
        is_referral: Whether this is a referral request
    """
    client_ip = request.client.host
    
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    try:
        print(f"Received {source} submission from {name} ({email})")
        
        # Basic validation
        if not name or not email or source not in ["form", "chatbot"]:
            raise HTTPException(status_code=400, detail="Missing required fields: name, email, and valid source are required")
        
        # Source-specific validation
        if source == "form" and not about_case:
            raise HTTPException(status_code=400, detail="about_case is required for form submissions")
        
        if source == "chatbot" and (not case_type or not case_state):
            raise HTTPException(status_code=400, detail="case_type and case_state are required for chatbot submissions")
        
        # Apply spam filter only for form submissions
        if source == "form":
            is_spam = await check_for_spam(name, phone or "", email, about_case)
            
            if is_spam:
                print(f"Form submission from {name} ({email}) detected as SPAM - rejected")
                return {
                    "status": "rejected",
                    "reason": "Submission detected as spam",
                    "timestamp": datetime.now().isoformat()
                }
        
        # Prepare template variables based on source
        if source == "form":
            template_id = FORM_TEMPLATE_ID
            subject = "New Lead Form Filled Out"
            template_variables = {
                "lead_name": name,
                "lead_email": email,
                "lead_phone_number": phone or "",
                "lead_case_description": about_case
            }
            case_info_for_sms = f"Case: {about_case[:50]}..." if len(about_case) > 50 else about_case
            
        else:  # chatbot
            template_id = CHATBOT_TEMPLATE_ID
            subject = "New Lead Alert"
            template_variables = {
                "lead_name": name,
                "lead_phone_number": phone or "",
                "lead_case_type": case_type,
                "lead_case_state": case_state
            }
            case_info_for_sms = f"{case_type} case in {case_state}"
        
        # Send email notification to the firm (not the lead)
        if not FIRM_NOTIFICATION_EMAIL:
            raise HTTPException(status_code=500, detail="FIRM_NOTIFICATION_EMAIL environment variable not configured")
            
        email_result = await send_email_via_mailersend(
            to_email=FIRM_NOTIFICATION_EMAIL,  # Send to firm's email
            to_name="Roth Davies Law Firm",
            template_id=template_id,
            subject=subject,
            variables=template_variables
        )
        
        if not email_result['success']:
            print(f"Email send failed: {email_result.get('error', 'Unknown error')}")
            await send_error_alert(f"Email send failed: {email_result.get('error', 'Unknown error')}", "/submit-lead")
        
        # Send SMS notification
        sms_success = await send_sms_notification(
            phone_number=phone or "No phone provided",
            user_name=name,
            source=source,
            case_info=case_info_for_sms,
            is_referral=is_referral
        )
        
        # Prepare unified webhook data
        webhook_data = {
            'source': source,
            'name': name,
            'phone': phone or "",
            'email': email,
            'about_case': about_case or "",  # Form field, empty for chatbot
            'case_type': case_type or "",    # Chatbot field, empty for form
            'case_state': case_state or "",  # Chatbot field, empty for form
            'is_referral': str(is_referral).lower(),
            'timestamp': datetime.now().isoformat()
        }
        
        # Send to webhook
        webhook_result = await send_to_webhook(webhook_data)
        
        if webhook_result['success']:
            print(f"{source.title()} submission from {name} ({email}) successfully processed and forwarded")
            
            return {
                "status": "success",
                "message": f"{source.title()} lead submitted successfully",
                "email_sent": email_result['success'],
                "sms_sent": sms_success,
                "webhook_response": webhook_result['response'],
                "timestamp": datetime.now().isoformat()
            }
        else:
            print(f"Failed to forward {source} submission from {name} ({email}) to webhook")
            print(f"Webhook failure details: {webhook_result}")
            
            # Use the effective status code (parsed from content if available)
            effective_status_code = webhook_result.get('effective_status_code', 500)
            
            # Include webhook response details in error
            raise HTTPException(
                status_code=effective_status_code, 
                detail={
                    "message": "Failed to process submission",
                    "email_sent": email_result['success'],
                    "sms_sent": sms_success,
                    "webhook_error": webhook_result
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error processing {source} submission: {e}")
        await send_error_alert(f"Lead submission error: {str(e)}", "/submit-lead")
        raise HTTPException(status_code=500, detail="Internal server error")

# ----- REMAINING ENDPOINTS -----

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

@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Law Firm Chatbot API"
    }

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

    # MailerSend variables (required for email functionality)
    mailersend_env_vars = [
        "MAILERSEND_API_KEY",
        "MAILERSEND_FROM_EMAIL",
        "FIRM_NOTIFICATION_EMAIL"  # ADD THIS LINE
    ]

    # Template ID variables
    template_env_vars = [
        "FORM_TEMPLATE_ID",
        "CHATBOT_TEMPLATE_ID"
    ]

    # Optional MailerSend variables
    optional_mailersend_vars = [
        "MAILERSEND_FROM_NAME"
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        print(f"WARNING: Missing required environment variables: {', '.join(missing_vars)}")

    missing_mailersend_vars = [var for var in mailersend_env_vars if not os.getenv(var)]
    if missing_mailersend_vars:
        print(f"WARNING: Missing MailerSend environment variables: {', '.join(missing_mailersend_vars)}")
        print("Email functionality will not work without these variables.")

    missing_template_vars = [var for var in template_env_vars if not os.getenv(var)]
    if missing_template_vars:
        print(f"WARNING: Missing template ID environment variables: {', '.join(missing_template_vars)}")
        print("Using default template IDs from code.")

    missing_optional_vars = [var for var in optional_mailersend_vars if not os.getenv(var)]
    if missing_optional_vars:
        print(f"INFO: Optional MailerSend environment variables not set: {', '.join(missing_optional_vars)}")
    
    uvicorn.run(app, host="0.0.0.0", port=10000)