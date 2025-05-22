from fastapi import FastAPI, Form
from typing import Optional
from playwright.sync_api import sync_playwright
import uvicorn

app = FastAPI()

# ----- FastAPI Route -----
@app.post("/submit-lead")
def submit_lead(
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    email: str = Form(...),
    about_case: str = Form(...)
):
    result = submit_to_ghl_form(name, phone, email, about_case)
    return {"status": "submitted", "success": result}

# ----- Debug Route to Inspect Form -----
@app.get("/debug-form")
def debug_form():
    result = inspect_form_structure()
    return {"form_structure": result}

def inspect_form_structure():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        
        # Create a more human-like browser context
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1366, 'height': 768}
        )
        
        page = context.new_page()
        
        # Remove webdriver traces
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            window.chrome = {
                runtime: {},
            };
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
        """)
        
        try:
            print("Loading page...")
            page.goto("https://camrenhall.github.io/roth-davies-form-public/")
            
            # Wait for the main iframe to load (updated form ID again)
            page.wait_for_selector('iframe#inline-YQRZjsrjVEFdk2pArn6b', timeout=15000)
            print("Main iframe found")
            
            # Wait longer for iframe content to load
            page.wait_for_timeout(8000)
            
            # Find the form frame
            frame = None
            for f in page.frames:
                try:
                    if f.url and ("leadconnectorhq.com" in f.url or "YQRZjsrjVEFdk2pArn6b" in f.url):
                        print(f"Found frame with URL: {f.url}")
                        frame = f
                        break
                except Exception as e:
                    print(f"Error checking frame: {e}")
            
            if not frame:
                return {"error": "Could not find form frame"}
            
            # Wait for form elements to load
            page.wait_for_timeout(5000)
            
            # Get comprehensive form structure
            form_structure = frame.evaluate("""
                () => {
                    const formElements = Array.from(document.querySelectorAll('input, textarea, select, button'));
                    
                    const structure = {
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
                        frameUrl: window.location.href
                    };
                    
                    return structure;
                }
            """)
            
            return form_structure
            
        except Exception as e:
            print(f"Error inspecting form: {e}")
            return {"error": str(e)}
        finally:
            try:
                context.close()
            except:
                pass
            browser.close()

# ----- Fixed Playwright Automation Based on Actual Form Structure -----
def submit_to_ghl_form(name, phone, email, about_case):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print("Loading page for form submission...")
            page.goto("https://camrenhall.github.io/roth-davies-form-public/")
            
            # Wait for the main iframe to load (updated form ID again)
            page.wait_for_selector('iframe#inline-YQRZjsrjVEFdk2pArn6b', timeout=15000)
            print("Main iframe loaded")
            
            # Wait for iframe content to fully load
            page.wait_for_timeout(8000)
            
            # Find the form frame
            frame = None
            for f in page.frames:
                try:
                    if f.url and ("leadconnectorhq.com" in f.url or "YQRZjsrjVEFdk2pArn6b" in f.url):
                        print(f"Found form frame: {f.url}")
                        frame = f
                        break
                except Exception:
                    continue
            
            if not frame:
                print("ERROR: Could not find form frame")
                return False
            
            # Wait for form to be ready
            page.wait_for_timeout(3000)
            
            # Verify form elements are present (try multiple possible field names)
            try:
                # Try to find any common form fields
                selectors_to_try = [
                    'input[name="full_name"]',  # Updated field name
                    'input[name="name"]', 
                    'input[type="text"]',
                    'input[type="email"]'
                ]
                
                form_ready = False
                for selector in selectors_to_try:
                    try:
                        frame.wait_for_selector(selector, timeout=3000)
                        print(f"Found form element: {selector}")
                        form_ready = True
                        break
                    except:
                        continue
                
                if not form_ready:
                    print("No recognizable form elements found")
                    return False
                else:
                    print("Form elements are ready")
                    
            except Exception as e:
                print(f"Form elements not ready: {e}")
                return False
            
            success_count = 0
            
            # Fill the name field (now properly named "full_name")
            try:
                frame.fill('input[name="full_name"]', name, timeout=5000)
                print(f"✓ Filled name field: {name}")
                success_count += 1
            except Exception as e:
                print(f"✗ Failed to fill name field: {e}")
                return False  # Name is required
            
            # Fill the email field
            try:
                frame.fill('input[name="email"]', email, timeout=5000)
                print(f"✓ Filled email field: {email}")
                success_count += 1
            except Exception as e:
                print(f"✗ Failed to fill email field: {e}")
                return False  # Email is required
            
            # Fill the phone field (now properly named "phone")
            if phone:
                try:
                    frame.fill('input[name="phone"]', phone, timeout=5000)
                    print(f"✓ Filled phone field: {phone}")
                    success_count += 1
                except Exception as e:
                    print(f"⚠ Failed to fill phone field: {e}")
                    # Phone is optional, so continue
            
            # Fill the case description (textarea with new ID)
            try:
                frame.fill('textarea[name="YzYpYdqxuttqzK5GsJDW"]', about_case, timeout=5000)
                print(f"✓ Filled case description field")
                success_count += 1
            except Exception as e:
                print(f"⚠ Failed to fill case description field: {e}")
                # Continue even if this fails
            
            print(f"Successfully filled {success_count} fields")
            
            # Check for CAPTCHA and all form elements before submitting
            try:
                detailed_form_check = frame.evaluate("""
                    () => {
                        const bodyText = document.body.textContent;
                        const allElements = Array.from(document.querySelectorAll('*'));
                        
                        // Look for CAPTCHA elements - fix the className bug
                        const captchaElements = allElements.filter(el => {
                            const className = el.className || '';
                            const id = el.id || '';
                            const classNameStr = typeof className === 'string' ? className : className.toString();
                            const idStr = typeof id === 'string' ? id : id.toString();
                            
                            return classNameStr.toLowerCase().includes('captcha') ||
                                   classNameStr.toLowerCase().includes('recaptcha') ||
                                   idStr.toLowerCase().includes('captcha') ||
                                   idStr.toLowerCase().includes('recaptcha') ||
                                   (el.tagName === 'IFRAME' && el.src && el.src.includes('recaptcha'));
                        });
                        
                        // Get submit button state
                        const submitButton = document.querySelector('button[type="submit"]');
                        
                        return {
                            bodyTextContainsCaptcha: bodyText.toLowerCase().includes('captcha'),
                            bodyTextContainsRecaptcha: bodyText.toLowerCase().includes('recaptcha'),
                            captchaElementsFound: captchaElements.length,
                            submitButtonDisabled: submitButton ? submitButton.disabled : null,
                            submitButtonText: submitButton ? submitButton.textContent.trim() : null,
                            captchaContextBefore: bodyText.toLowerCase().indexOf('captcha') >= 0 ? 
                                bodyText.substring(Math.max(0, bodyText.toLowerCase().indexOf('captcha') - 50), bodyText.toLowerCase().indexOf('captcha') + 100) : 'No captcha found',
                            entireBodyText: bodyText.substring(0, 2000)  // First 2000 chars
                        };
                    }
                """)
                
                print(f"=== DETAILED CAPTCHA ANALYSIS ===")
                print(f"Body text contains 'captcha': {detailed_form_check.get('bodyTextContainsCaptcha')}")
                print(f"Body text contains 'recaptcha': {detailed_form_check.get('bodyTextContainsRecaptcha')}")
                print(f"CAPTCHA elements found: {detailed_form_check.get('captchaElementsFound')}")
                print(f"Submit button disabled: {detailed_form_check.get('submitButtonDisabled')}")
                print(f"Submit button text: {detailed_form_check.get('submitButtonText')}")
                print(f"CAPTCHA context: '{detailed_form_check.get('captchaContextBefore')}'")
                
                print(f"=== FULL BODY TEXT (first 2000 chars) ===")
                print(detailed_form_check.get('entireBodyText', ''))
                print("=== END BODY TEXT ===")
                
            except Exception as e:
                print(f"Error in detailed form check: {e}")
                import traceback
                traceback.print_exc()
            
            # Take a screenshot before submitting (for debugging)
            try:
                page.screenshot(path="/tmp/before_submit.png")
                print("Screenshot taken before submit")
            except:
                pass
            
            # Submit the form with more detailed monitoring
            try:
                print("Attempting to click submit button...")
                
                # Wait a moment to ensure form is ready
                page.wait_for_timeout(1000)
                
                # Try to click submit and monitor the response
                frame.click('button[type="submit"]', timeout=5000)
                print("✓ Submit button clicked")
                
                # Monitor for immediate changes
                page.wait_for_timeout(2000)
                
                # Check if form disappeared or changed
                form_check = frame.evaluate("""
                    () => {
                        const submitButton = document.querySelector('button[type="submit"]');
                        const fullNameField = document.querySelector('input[name="full_name"]');
                        return {
                            submitButtonExists: submitButton !== null,
                            submitButtonDisabled: submitButton ? submitButton.disabled : null,
                            submitButtonText: submitButton ? submitButton.textContent.trim() : null,
                            fullNameFieldExists: fullNameField !== null,
                            fullNameFieldValue: fullNameField ? fullNameField.value : null
                        };
                    }
                """)
                print(f"Form state after submit click: {form_check}")
                
                # Wait longer for potential processing
                print("Waiting for form processing...")
                page.wait_for_timeout(8000)
                
                # Take screenshot after submitting
                try:
                    page.screenshot(path="/tmp/after_submit.png")
                    print("Screenshot taken after submit")
                except:
                    pass
                
            except Exception as e:
                print(f"✗ Failed to click submit button: {e}")
                return False
            
            # Comprehensive success detection
            try:
                print("Checking for submission success indicators...")
                
                success_check = frame.evaluate("""
                    () => {
                        const bodyText = document.body.textContent.toLowerCase();
                        const fullBodyText = document.body.textContent;
                        const submitButton = document.querySelector('button[type="submit"]');
                        const fullNameField = document.querySelector('input[name="full_name"]');
                        
                        return {
                            bodyTextSample: bodyText.substring(0, 800),
                            fullBodyTextLength: fullBodyText.length,
                            formFieldsStillVisible: fullNameField !== null,
                            submitButtonExists: submitButton !== null,
                            submitButtonText: submitButton ? submitButton.textContent.trim() : null,
                            submitButtonDisabled: submitButton ? submitButton.disabled : null,
                            hasThankYou: bodyText.includes('thank you') || bodyText.includes('thanks'),
                            hasSuccess: bodyText.includes('success') || bodyText.includes('submitted') || bodyText.includes('received'),
                            hasError: bodyText.includes('error') || bodyText.includes('failed') || bodyText.includes('invalid'),
                            currentUrl: window.location.href,
                            documentTitle: document.title
                        };
                    }
                """)
                
                print(f"=== DETAILED SUCCESS CHECK ===")
                print(f"Form fields still visible: {success_check.get('formFieldsStillVisible')}")
                print(f"Submit button exists: {success_check.get('submitButtonExists')}")
                print(f"Submit button text: {success_check.get('submitButtonText')}")
                print(f"Submit button disabled: {success_check.get('submitButtonDisabled')}")
                print(f"Has thank you message: {success_check.get('hasThankYou')}")
                print(f"Has success indicators: {success_check.get('hasSuccess')}")
                print(f"Has error indicators: {success_check.get('hasError')}")
                print(f"Current URL: {success_check.get('currentUrl')}")
                print(f"Document title: {success_check.get('documentTitle')}")
                print(f"Body text sample: {success_check.get('bodyTextSample', '')[:300]}...")
                
                # More strict success criteria - fix Python string method bug
                if 'captcha' in success_check.get('bodyText', '').lower() or 'recaptcha' in success_check.get('bodyText', '').lower():
                    print("✗ FAILURE: CAPTCHA is blocking submission")
                    print("Found CAPTCHA requirement in page text")
                    return False
                elif success_check.get('hasThankYou') or success_check.get('hasSuccess'):
                    print("✓ SUCCESS: Found success indicators in page text")
                    return True
                elif not success_check.get('formFieldsStillVisible'):
                    print("✓ SUCCESS: Form fields disappeared (likely successful)")
                    return True
                elif success_check.get('hasError'):
                    print("✗ FAILURE: Error indicators found")
                    return False
                elif success_count >= 2:
                    print("⚠ UNCERTAIN: Fields filled and submitted, but no clear success indicators")
                    print("This might be successful, but we can't confirm from the page response")
                    return False  # Changed to False since CAPTCHA is likely blocking
                else:
                    print("✗ FAILURE: Not enough fields filled")
                    return False
                    
            except Exception as e:
                print(f"Error during success check: {e}")
                import traceback
                traceback.print_exc()
                return success_count >= 2
            
        except Exception as e:
            print(f"Error submitting form: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            browser.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)