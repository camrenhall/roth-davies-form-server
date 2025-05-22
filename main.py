from fastapi import FastAPI, Form, HTTPException
from typing import Optional
import uvicorn
import requests
import json
import openai
import os
from datetime import datetime

app = FastAPI()

# Configure OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

# Webhook URL
ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/22987863/2j3r1l5/"

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
- Test submissions with names like "Test", "Camren", etc. are legitimate for testing purposes
- Focus on the case description content more than contact info formatting
- Consider that real people may have typos, brief descriptions, or unusual circumstances

Respond with ONLY one word: "SPAM" or "LEGITIMATE"

Examples:
- "I was in a car accident last week and need help" → LEGITIMATE
- "We offer SEO services to grow your law firm" → SPAM  
- "My husband filed for divorce, need attorney" → LEGITIMATE
- "Make money from home with crypto trading" → SPAM
- "Got arrested for DUI last night" → LEGITIMATE
- "Test case description" → LEGITIMATE (testing purposes)
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
        # If OpenAI fails, err on the side of caution and allow the submission
        print("Spam detection failed, allowing submission through")
        return False

async def send_to_webhook(name: str, phone: str, email: str, about_case: str) -> bool:
    """
    Send the legitimate submission to the Zapier webhook.
    Returns True if successful, False if failed.
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
        
        # Send POST request to Zapier webhook
        response = requests.post(
            ZAPIER_WEBHOOK_URL,
            data=form_data,
            timeout=30
        )
        
        if response.status_code == 200:
            print("Successfully sent to webhook")
            return True
        else:
            print(f"Webhook failed with status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"Error sending to webhook: {e}")
        return False

# ----- Main API Endpoint -----
@app.post("/submit-lead")
async def submit_lead(
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    email: str = Form(...),
    about_case: str = Form(...)
):
    """
    Main endpoint that filters spam and forwards legitimate submissions to webhook.
    """
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
        
        # Send legitimate submission to webhook
        webhook_success = await send_to_webhook(name, phone or "", email, about_case)
        
        if webhook_success:
            print(f"Submission from {name} ({email}) successfully processed and forwarded")
            return {
                "status": "success",
                "message": "Lead submitted successfully",
                "timestamp": datetime.now().isoformat()
            }
        else:
            print(f"Failed to forward submission from {name} ({email}) to webhook")
            raise HTTPException(status_code=500, detail="Failed to process submission")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error processing submission: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# ----- Health Check Endpoint -----
@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Law Firm Spam Filter API"
    }

# ----- Test Endpoint for Spam Detection -----
@app.post("/test-spam-detection")
async def test_spam_detection(
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    email: str = Form(...),
    about_case: str = Form(...)
):
    """
    Test endpoint to check spam detection without sending to webhook.
    """
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
    # Check for required environment variable
    if not os.getenv("OPENAI_API_KEY"):
        print("WARNING: OPENAI_API_KEY environment variable not set")
    
    uvicorn.run(app, host="0.0.0.0", port=10000)