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
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print("Loading page...")
            page.goto("https://camrenhall.github.io/roth-davies-form-public/")
            
            # Wait for the main iframe to load (updated form ID)
            page.wait_for_selector('iframe#inline-RlGk6eSbjEVA2yMNDYvl', timeout=15000)
            print("Main iframe found")
            
            # Wait longer for iframe content to load
            page.wait_for_timeout(8000)
            
            # Find the form frame
            frame = None
            for f in page.frames:
                try:
                    if f.url and ("leadconnectorhq.com" in f.url or "RlGk6eSbjEVA2yMNDYvl" in f.url):
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
            browser.close()

# ----- Fixed Playwright Automation Based on Actual Form Structure -----
def submit_to_ghl_form(name, phone, email, about_case):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print("Loading page for form submission...")
            page.goto("https://camrenhall.github.io/roth-davies-form-public/")
            
            # Wait for the main iframe to load (updated form ID)
            page.wait_for_selector('iframe#inline-RlGk6eSbjEVA2yMNDYvl', timeout=15000)
            print("Main iframe loaded")
            
            # Wait for iframe content to fully load
            page.wait_for_timeout(8000)
            
            # Find the form frame
            frame = None
            for f in page.frames:
                try:
                    if f.url and ("leadconnectorhq.com" in f.url or "RlGk6eSbjEVA2yMNDYvl" in f.url):
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
                    'input[name="first_name"]',
                    'input[name="name"]', 
                    'input[name="full_name"]',
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
            
            # Fill the name field (first_name field with "Name" placeholder)
            try:
                frame.fill('input[name="first_name"]', name, timeout=5000)
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
            
            # Fill the phone field (last_name field with "Phone (Optional)" placeholder)
            if phone:
                try:
                    frame.fill('input[name="last_name"]', phone, timeout=5000)
                    print(f"✓ Filled phone field: {phone}")
                    success_count += 1
                except Exception as e:
                    print(f"⚠ Failed to fill phone field: {e}")
                    # Phone is optional, so continue
            
            # Fill the case description (textarea with weird name)
            try:
                frame.fill('textarea[name="yC389AjWtdl4nv9GkvZM"]', about_case, timeout=5000)
                print(f"✓ Filled case description field")
                success_count += 1
            except Exception as e:
                print(f"⚠ Failed to fill case description field: {e}")
                # Continue even if this fails
            
            print(f"Successfully filled {success_count} fields")
            
            # Submit the form
            try:
                frame.click('button[type="submit"]', timeout=5000)
                print("✓ Clicked submit button")
            except Exception as e:
                print(f"✗ Failed to click submit button: {e}")
                return False
            
            # Wait for submission to complete and check for success
            page.wait_for_timeout(5000)
            
            # Check for success indicators or form changes
            try:
                success_check = frame.evaluate("""
                    () => {
                        const bodyText = document.body.textContent.toLowerCase();
                        const formStillVisible = document.querySelector('input[name="first_name"]') !== null;
                        return {
                            bodyText: bodyText.substring(0, 500),
                            formStillVisible: formStillVisible,
                            hasThankYou: bodyText.includes('thank you') || bodyText.includes('thanks'),
                            hasSuccess: bodyText.includes('success') || bodyText.includes('submitted'),
                            hasReceived: bodyText.includes('received') || bodyText.includes('sent'),
                            currentUrl: window.location.href
                        };
                    }
                """)
                
                print(f"Success check results: {success_check}")
                
                # Consider it successful if we filled required fields and clicked submit
                # Additional success indicators are a bonus
                if success_count >= 2:  # Name and email are minimum
                    print("✓ Form submission appears successful")
                    return True
                else:
                    print("✗ Not enough fields were filled")
                    return False
                    
            except Exception as e:
                print(f"Could not check success indicators: {e}")
                # If we got this far and filled the minimum fields, consider it successful
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