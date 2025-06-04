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

# Resend configuration
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL")
RESEND_FROM_NAME = os.getenv("RESEND_FROM_NAME", "Roth Davies Law Firm")
FIRM_NOTIFICATION_EMAIL = os.getenv("FIRM_NOTIFICATION_EMAIL")

# Webhook URL
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")

# Rate limiting storage (in production, use Redis)
rate_limit_storage = defaultdict(list)
RATE_LIMIT_REQUESTS = 100  # requests per window
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds

def get_form_email_template(lead_name: str, lead_phone: str, lead_email: str, lead_case_description: str) -> str:
    """Generate HTML template for form submissions"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>New Lead Form Submission</title>
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            
            <!-- Logo -->
            <div style="text-align: center; margin-bottom: 40px;">
                <div style="display: inline-block; background-color: #1a365d; color: white; padding: 15px 25px; border-radius: 4px;">
                    <div style="font-size: 24px; font-weight: bold; letter-spacing: 1px;">ROTH DAVIES</div>
                    <div style="font-size: 12px; letter-spacing: 2px; margin-top: 5px; border-top: 1px solid #ffffff; padding-top: 5px;">TRIAL LAWYERS</div>
                </div>
            </div>
            
            <!-- Main Content -->
            <h1 style="color: #333333; font-size: 28px; margin-bottom: 20px; text-align: center;">A new lead has filled out the form!</h1>
            
            <p style="color: #555555; font-size: 16px; line-height: 1.6; margin-bottom: 30px;">
                A new potential client has filled out the "Get In Touch With Us!" form on the website. 
                Their contact details are listed below, and are stored in HighLevel for your viewing.
            </p>
            
            <h2 style="color: #333333; font-size: 20px; margin-bottom: 20px;">Lead Information:</h2>
            
            <ul style="color: #555555; font-size: 16px; line-height: 1.8; padding-left: 20px;">
                <li><strong>Name:</strong> {lead_name}</li>
                <li><strong>Phone:</strong> {lead_phone}</li>
                <li><strong>Email:</strong> <a href="mailto:{lead_email}" style="color: #1a365d; text-decoration: none;">{lead_email}</a></li>
                <li><strong>Case Description:</strong> {lead_case_description}</li>
            </ul>
            
        </div>
    </body>
    </html>
    """

def get_chatbot_email_template(lead_name: str, lead_phone: str, lead_case_type: str, lead_case_state: str, case_description: str = None) -> str:
    """Generate HTML template for chatbot submissions"""
    
    # Build case info list
    case_info_items = [
        f"<li><strong>Name:</strong> {lead_name}</li>",
        f"<li><strong>Phone:</strong> {lead_phone}</li>",
        f"<li><strong>Case Type:</strong> {lead_case_type}</li>",
        f"<li><strong>Case State:</strong> {lead_case_state}</li>"
    ]
    
    # Add case description if provided
    if case_description and case_description.strip():
        case_info_items.append(f"<li><strong>Case Description:</strong> {case_description}</li>")
    
    case_info_html = "\n                ".join(case_info_items)
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>New Lead Chatbot Interaction</title>
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            
            <!-- Logo -->
            <div style="text-align: center; margin-bottom: 40px;">
                <div style="display: inline-block; background-color: #1a365d; color: white; padding: 15px 25px; border-radius: 4px;">
                    <div style="font-size: 24px; font-weight: bold; letter-spacing: 1px;">ROTH DAVIES</div>
                    <div style="font-size: 12px; letter-spacing: 2px; margin-top: 5px; border-top: 1px solid #ffffff; padding-top: 5px;">TRIAL LAWYERS</div>
                </div>
            </div>
            
            <!-- Main Content -->
            <h1 style="color: #333333; font-size: 28px; margin-bottom: 20px; text-align: center;">A new lead has used the Chatbot!</h1>
            
            <p style="color: #555555; font-size: 16px; line-height: 1.6; margin-bottom: 30px;">
                A new potential client has interacted with the Chatbot on the website. 
                Their contact details are listed below, and are stored in HighLevel for your viewing.
            </p>
            
            <h2 style="color: #333333; font-size: 20px; margin-bottom: 20px;">Lead Information:</h2>
            
            <ul style="color: #555555; font-size: 16px; line-height: 1.8; padding-left: 20px;">
                {case_info_html}
            </ul>
            
        </div>
    </body>
    </html>
    """

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

async def send_email_via_resend(
    to_email: str,
    subject: str,
    html_content: str,
    from_name: Optional[str] = None
) -> dict:
    """
    Send email via Resend API.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML content of the email
        from_name: Custom sender name (optional)
    
    Returns:
        dict: Response with success status and details
    """
    try:
        if not RESEND_API_KEY:
            raise Exception("RESEND_API_KEY not configured")
        
        if not RESEND_FROM_EMAIL:
            raise Exception("RESEND_FROM_EMAIL not configured")
        
        # Prepare sender
        sender_name = from_name or RESEND_FROM_NAME
        from_address = f"{sender_name} <{RESEND_FROM_EMAIL}>"
        
        # Prepare request payload
        payload = {
            "from": from_address,
            "to": [to_email],
            "subject": subject,
            "html": html_content
        }
        
        print(f"Sending email via Resend to: {to_email}")
        print(f"Subject: {subject}")
        
        # Send request to Resend API
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )
        
        # Check for success (any 2xx status code)
        if 200 <= response.status_code < 300:
            print("Email sent successfully via Resend")
            return {
                "success": True,
                "message": "Email sent successfully",
                "status_code": response.status_code,
                "response_data": response.json() if response.text else None,
                "timestamp": datetime.now().isoformat()
            }
        else:
            error_msg = f"Resend API returned status {response.status_code}: {response.text}"
            print(f"Email send error: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "status_code": response.status_code,
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        error_msg = f"Error sending email via Resend: {str(e)}"
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
    # Unified case description field for both form and chatbot
    about_case: Optional[str] = Form(None),  # Now used by both form and chatbot
    # Chatbot-specific fields (kept for backward compatibility)
    case_type: Optional[str] = Form(None),  # Chatbot case type
    case_state: Optional[str] = Form(None),  # Chatbot case state/location
    # Optional fields
    is_referral: bool = Form(False)
):
    """
    Consolidated endpoint that handles both form and chatbot lead submissions.
    Now both sources include case descriptions in the about_case field.
    Spam detection happens BEFORE detailed validation to prevent spam from causing HTTP errors.
    """
    client_ip = request.client.host
    
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    try:
        print(f"Received {source} submission from {name} ({email})")
        
        # BASIC validation first (only the absolute minimum to prevent crashes)
        if not name or source not in ["form", "chatbot"]:
            raise HTTPException(status_code=400, detail="Missing required fields: name and valid source are required")
        
        # SPAM DETECTION FIRST - before detailed validation
        # This prevents spam from causing validation errors in logs
        if source == "form":
            # For spam detection, treat missing fields as empty strings to avoid crashes
            spam_name = name or ""
            spam_phone = phone or ""
            spam_email = email or ""
            spam_case = about_case or ""
            
            is_spam = await check_for_spam(spam_name, spam_phone, spam_email, spam_case)
            
            if is_spam:
                print(f"SPAM DETECTED: Form submission from {name} ({email}) - rejected silently")
                # Return fake success to avoid giving spammers feedback about detection
                return {
                    "status": "success",  # Lie to the spammer
                    "message": "Form submitted successfully",
                    "timestamp": datetime.now().isoformat()
                }
        
        # DETAILED VALIDATION ONLY AFTER spam filtering
        # Now we know it's legitimate, so validation errors represent real issues
        
        # Log the complete request data for debugging legitimate submissions
        request_data = {
            "source": source,
            "name": name,
            "email": email,
            "phone": phone,
            "about_case": about_case,
            "case_type": case_type,
            "case_state": case_state,
            "is_referral": is_referral
        }
        print(f"Processing legitimate {source} submission with data: {request_data}")
        
        # Email is only required for form submissions
        if source == "form" and not email:
            print(f"VALIDATION ERROR: Email missing for form submission. Request data: {request_data}")
            raise HTTPException(status_code=400, detail="Email is required for form submissions")
        
        # about_case is now required for both sources
        if not about_case:
            print(f"VALIDATION ERROR: Case description missing. Request data: {request_data}")
            raise HTTPException(status_code=400, detail="Case description is required for all submissions")
        
        # Chatbot-specific validation (still need case_type and case_state for chatbot)
        if source == "chatbot" and (not case_type or not case_state):
            print(f"VALIDATION ERROR: Missing chatbot fields. case_type='{case_type}', case_state='{case_state}'. Request data: {request_data}")
            raise HTTPException(status_code=400, detail="case_type and case_state are required for chatbot submissions")
        
        # Prepare email content based on source
        if source == "form":
            subject = "New Lead Form Filled Out"
            case_info_for_sms = f"Case: {about_case[:50]}..." if len(about_case) > 50 else about_case
            
            html_content = get_form_email_template(
                lead_name=name,
                lead_phone=phone or "Not provided",
                lead_email=email,
                lead_case_description=about_case
            )
            
        else:  # chatbot
            subject = "New Lead Alert"
            case_info_for_sms = f"{case_type} case in {case_state}: {about_case[:30]}..." if len(about_case) > 30 else f"{case_type} case in {case_state}: {about_case}"
            
            html_content = get_chatbot_email_template(
                lead_name=name,
                lead_phone=phone or "Not provided", 
                lead_case_type=case_type,
                lead_case_state=case_state,
                case_description=about_case  # Pass the case description
            )
        
        # Send email notification to the firm
        if not FIRM_NOTIFICATION_EMAIL:
            raise HTTPException(status_code=500, detail="FIRM_NOTIFICATION_EMAIL environment variable not configured")
        
        email_result = await send_email_via_resend(
            to_email=FIRM_NOTIFICATION_EMAIL,
            subject=subject,
            html_content=html_content
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
        
        # Prepare unified webhook data (about_case now populated for both sources)
        webhook_data = {
            'source': source,
            'name': name,
            'phone': phone or "",
            'email': email,
            'about_case': about_case,  # Now contains case description for both sources
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

    # Resend variables (required for email functionality)
    resend_env_vars = [
        "RESEND_API_KEY",
        "RESEND_FROM_EMAIL", 
        "FIRM_NOTIFICATION_EMAIL"
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

    missing_resend_vars = [var for var in resend_env_vars if not os.getenv(var)]
    if missing_resend_vars:
        print(f"WARNING: Missing Resend environment variables: {', '.join(missing_resend_vars)}")
        print("Email functionality will not work without these variables.")
        
    missing_template_vars = [var for var in template_env_vars if not os.getenv(var)]
    if missing_template_vars:
        print(f"WARNING: Missing template ID environment variables: {', '.join(missing_template_vars)}")
        print("Using default template IDs from code.")

    missing_optional_vars = [var for var in optional_mailersend_vars if not os.getenv(var)]
    if missing_optional_vars:
        print(f"INFO: Optional MailerSend environment variables not set: {', '.join(missing_optional_vars)}")
    
    uvicorn.run(app, host="0.0.0.0", port=10000)