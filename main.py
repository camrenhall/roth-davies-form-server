from fastapi import FastAPI, Form
from typing import Optional
from playwright.sync_api import sync_playwright
import uvicorn
import json

app = FastAPI()

# ----- FastAPI Route -----
@app.post("/submit-lead")
def submit_lead(
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    email: str = Form(...),
    about_case: str = Form(...)
):
    # Use the full name as provided - don't split it
    result = submit_to_ghl_form(name, phone, email, about_case)
    return {"status": "submitted", "success": result}

# ----- Debug Route to Inspect Form -----
@app.get("/debug-form")
def debug_form():
    result = inspect_form_structure()
    return {"form_structure": result}

def inspect_form_structure():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print("Loading page...")
            page.goto("https://camrenhall.github.io/roth-davies-form-public/")
            
            # Wait for the main iframe to load
            page.wait_for_selector('iframe#inline-UQVFhuQiNCfdJTydbFrm', timeout=15000)
            print("Main iframe found")
            
            # Wait longer for iframe content to load
            page.wait_for_timeout(8000)
            
            # Find the form frame
            frame = None
            for f in page.frames:
                try:
                    if f.url and ("leadconnectorhq.com" in f.url or "UQVFhuQiNCfdJTydbFrm" in f.url):
                        print(f"Found frame with URL: {f.url}")
                        frame = f
                        break
                except Exception as e:
                    print(f"Error checking frame: {e}")
            
            if not frame:
                print("No matching frame found. Available frames:")
                for i, f in enumerate(page.frames):
                    try:
                        print(f"Frame {i}: {f.url}")
                    except:
                        print(f"Frame {i}: Unable to get URL")
                return {"error": "Could not find form frame"}
            
            # Wait for any form elements to load
            page.wait_for_timeout(5000)
            
            # Get comprehensive form structure
            form_structure = frame.evaluate("""
                () => {
                    // Get all form elements
                    const allElements = Array.from(document.querySelectorAll('*'));
                    const formElements = allElements.filter(el => 
                        ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'FORM'].includes(el.tagName)
                    );
                    
                    const structure = {
                        totalElements: allElements.length,
                        formElements: formElements.map(el => ({
                            tagName: el.tagName,
                            type: el.type || 'N/A',
                            name: el.name || 'N/A',
                            id: el.id || 'N/A',
                            placeholder: el.placeholder || 'N/A',
                            className: el.className || 'N/A',
                            value: el.value || 'N/A',
                            required: el.required || false,
                            textContent: (el.textContent || '').trim().substring(0, 100),
                            outerHTML: el.outerHTML.substring(0, 300) + (el.outerHTML.length > 300 ? '...' : '')
                        })),
                        bodyHTML: document.body.innerHTML.substring(0, 1000) + '...',
                        documentReady: document.readyState,
                        frameUrl: window.location.href
                    };
                    
                    return structure;
                }
            """)
            
            print("=== FORM STRUCTURE ANALYSIS ===")
            print(f"Frame URL: {frame.url}")
            print(f"Total elements in frame: {form_structure.get('totalElements', 0)}")
            print(f"Form elements found: {len(form_structure.get('formElements', []))}")
            print(f"Document ready state: {form_structure.get('documentReady', 'unknown')}")
            
            print("\n=== FORM ELEMENTS ===")
            for i, element in enumerate(form_structure.get('formElements', [])):
                print(f"\nElement {i+1}:")
                print(f"  Tag: {element['tagName']}")
                print(f"  Type: {element['type']}")
                print(f"  Name: {element['name']}")
                print(f"  ID: {element['id']}")
                print(f"  Placeholder: {element['placeholder']}")
                print(f"  Class: {element['className']}")
                print(f"  Required: {element['required']}")
                print(f"  Text: {element['textContent'][:50]}...")
                print(f"  HTML: {element['outerHTML'][:150]}...")
            
            return form_structure
            
        except Exception as e:
            print(f"Error inspecting form: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}
        finally:
            browser.close()

# ----- Updated Playwright Automation -----
def submit_to_ghl_form(name, phone, email, about_case):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print("Loading page for form submission...")
            page.goto("https://camrenhall.github.io/roth-davies-form-public/")
            
            # Wait for the main iframe to load
            page.wait_for_selector('iframe#inline-UQVFhuQiNCfdJTydbFrm', timeout=15000)
            print("Main iframe loaded")
            
            # Wait longer for iframe content to fully load
            page.wait_for_timeout(8000)
            
            # Find the form frame
            frame = None
            for f in page.frames:
                try:
                    if f.url and ("leadconnectorhq.com" in f.url or "UQVFhuQiNCfdJTydbFrm" in f.url):
                        print(f"Found form frame: {f.url}")
                        frame = f
                        break
                except Exception:
                    continue
            
            if not frame:
                print("ERROR: Could not find form frame")
                # List all available frames for debugging
                for i, f in enumerate(page.frames):
                    try:
                        print(f"Available frame {i}: {f.url}")
                    except:
                        print(f"Available frame {i}: Unable to get URL")
                return False
            
            # Wait for form to be ready
            page.wait_for_timeout(3000)
            
            # Get all available form elements
            available_elements = frame.evaluate("""
                () => {
                    const elements = Array.from(document.querySelectorAll('input, textarea, select, button'));
                    return elements.map(el => ({
                        tagName: el.tagName,
                        type: el.type || 'N/A',
                        name: el.name || 'N/A',
                        id: el.id || 'N/A',
                        placeholder: el.placeholder || 'N/A',
                        className: el.className || 'N/A'
                    }));
                }
            """)
            print(f"Available form elements: {json.dumps(available_elements, indent=2)}")
            
            success_count = 0
            
            # Fill name field - try various selectors based on common patterns
            name_selectors = [
                'input[name="name"]',
                'input[name="full_name"]',
                'input[name="fullName"]',
                'input[placeholder*="name" i]',
                'input[placeholder*="Name" i]',
                'input[type="text"]:first-of-type',
                'input:first-of-type'
            ]
            
            name_filled = False
            for selector in name_selectors:
                try:
                    element = frame.query_selector(selector)
                    if element:
                        frame.fill(selector, name, timeout=5000)
                        print(f"✓ Filled name using: {selector}")
                        success_count += 1
                        name_filled = True
                        break
                except Exception as e:
                    print(f"Failed name selector {selector}: {e}")
            
            if not name_filled:
                print("⚠ Could not fill name field")
            
            # Fill email field
            email_selectors = [
                'input[name="email"]',
                'input[type="email"]',
                'input[placeholder*="email" i]',
                'input[placeholder*="Email" i]'
            ]
            
            email_filled = False
            for selector in email_selectors:
                try:
                    element = frame.query_selector(selector)
                    if element:
                        frame.fill(selector, email, timeout=5000)
                        print(f"✓ Filled email using: {selector}")
                        success_count += 1
                        email_filled = True
                        break
                except Exception as e:
                    print(f"Failed email selector {selector}: {e}")
            
            if not email_filled:
                print("⚠ Could not fill email field")
            
            # Fill phone field (optional)
            if phone:
                phone_selectors = [
                    'input[name="phone"]',
                    'input[type="tel"]',
                    'input[placeholder*="phone" i]',
                    'input[placeholder*="Phone" i]',
                    'input[placeholder*="number" i]'
                ]
                
                phone_filled = False
                for selector in phone_selectors:
                    try:
                        element = frame.query_selector(selector)
                        if element:
                            frame.fill(selector, phone, timeout=3000)
                            print(f"✓ Filled phone using: {selector}")
                            success_count += 1
                            phone_filled = True
                            break
                    except Exception as e:
                        print(f"Failed phone selector {selector}: {e}")
                
                if not phone_filled:
                    print("⚠ Phone field not found or couldn't be filled")
            
            # Fill message/case description
            message_selectors = [
                'textarea[name*="case"]',
                'textarea[name*="message"]',
                'textarea[name*="about"]',
                'textarea[name*="tell"]',
                'textarea[placeholder*="case" i]',
                'textarea[placeholder*="tell" i]',
                'textarea[placeholder*="about" i]',
                'textarea[placeholder*="message" i]',
                'textarea',  # Fallback to any textarea
                'input[name*="case"]',
                'input[name*="message"]'
            ]
            
            message_filled = False
            for selector in message_selectors:
                try:
                    element = frame.query_selector(selector)
                    if element:
                        frame.fill(selector, about_case, timeout=5000)
                        print(f"✓ Filled message using: {selector}")
                        success_count += 1
                        message_filled = True
                        break
                except Exception as e:
                    print(f"Failed message selector {selector}: {e}")
            
            if not message_filled:
                print("⚠ Could not fill message field")
            
            print(f"Successfully filled {success_count} fields")
            
            # Submit the form
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Submit")',
                'button:has-text("submit")',
                'button:has-text("Send")',
                'button[class*="submit" i]',
                'button'  # Fallback to any button
            ]
            
            submitted = False
            for selector in submit_selectors:
                try:
                    element = frame.query_selector(selector)
                    if element:
                        frame.click(selector, timeout=5000)
                        print(f"✓ Clicked submit using: {selector}")
                        submitted = True
                        break
                except Exception as e:
                    print(f"Failed submit selector {selector}: {e}")
            
            if not submitted:
                print("ERROR: Could not find or click submit button")
                return False
            
            # Wait for submission to complete
            page.wait_for_timeout(5000)
            print("Form submission attempted")
            
            # Check for success indicators
            try:
                # Look for common success messages or redirects
                success_indicators = frame.evaluate("""
                    () => {
                        const text = document.body.textContent.toLowerCase();
                        return {
                            hasThankYou: text.includes('thank you') || text.includes('thanks'),
                            hasSuccess: text.includes('success') || text.includes('submitted'),
                            hasReceived: text.includes('received') || text.includes('sent'),
                            currentUrl: window.location.href,
                            bodyText: document.body.textContent.substring(0, 500)
                        };
                    }
                """)
                print(f"Success indicators: {success_indicators}")
            except Exception as e:
                print(f"Could not check success indicators: {e}")
            
            return success_count >= 2  # Require at least name and email to be filled
            
        except Exception as e:
            print(f"Error submitting form: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            browser.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)