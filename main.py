from fastapi import FastAPI, Form
from typing import Optional
from playwright.sync_api import sync_playwright
import uvicorn
import time

app = FastAPI()

# ----- FastAPI Route -----
@app.post("/submit-lead")
def submit_lead(
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    email: str = Form(...),
    about_case: str = Form(...)
):
    # Split name into first/last if possible (GHL expects both)
    parts = name.strip().split()
    first_name = parts[0]
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
    # Now submit to the embedded GHL form
    result = submit_to_ghl_form(first_name, last_name, phone, email, about_case)
    return {"status": "submitted", "success": result}

# ----- Playwright Automation -----
def submit_to_ghl_form(first_name, last_name, phone, email, about_case):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto("https://camrenhall.github.io/roth-davies-form-public/")
            
            # Wait for the main iframe to load
            page.wait_for_selector('iframe#inline-UQVFhuQiNCfdJTydbFrm', timeout=10000)
            
            # Wait a bit longer for the iframe content to fully load
            page.wait_for_timeout(3000)
            
            # Function to get a fresh frame reference and fill form
            def fill_form_with_retries(max_retries=3):
                for attempt in range(max_retries):
                    try:
                        # Get fresh frame reference each time
                        frame = None
                        
                        # Find the correct frame
                        for f in page.frames:
                            try:
                                if f.url and "leadconnectorhq.com/widget/form/UQVFhuQiNCfdJTydbFrm" in f.url:
                                    # Check if the form inputs are available
                                    if f.query_selector('input[name="first_name"]'):
                                        frame = f
                                        break
                            except Exception:
                                continue
                        
                        if not frame:
                            if attempt < max_retries - 1:
                                print(f"Frame not found, retrying... (attempt {attempt + 1})")
                                page.wait_for_timeout(2000)
                                continue
                            else:
                                raise Exception("Could not find form frame after all retries")
                        
                        # Wait for form to be fully loaded
                        frame.wait_for_selector('input[name="first_name"]', timeout=5000)
                        
                        # Fill form fields one by one with error handling
                        try:
                            frame.fill('input[name="first_name"]', first_name)
                            frame.fill('input[name="last_name"]', last_name)
                            frame.fill('input[name="email"]', email)
                            
                            if phone:
                                # Phone field might be optional or have different selector
                                try:
                                    frame.fill('input[name="phone"]', phone)
                                except Exception as e:
                                    print(f"Phone field not found or couldn't be filled: {e}")
                            
                            # Fill the about case textarea
                            frame.fill('textarea[name="yC389AjWtdl4nv9GkvZM"]', about_case)
                            
                            # Submit the form
                            frame.click('button[type="submit"]')
                            
                            # Wait for submission to complete
                            page.wait_for_timeout(3000)
                            
                            return True
                            
                        except Exception as fill_error:
                            if "Frame was detached" in str(fill_error) and attempt < max_retries - 1:
                                print(f"Frame detached during filling, retrying... (attempt {attempt + 1})")
                                page.wait_for_timeout(2000)
                                continue
                            else:
                                raise fill_error
                                
                    except Exception as e:
                        if attempt < max_retries - 1:
                            print(f"Error on attempt {attempt + 1}: {e}")
                            page.wait_for_timeout(2000)
                            continue
                        else:
                            raise e
                
                return False
            
            # Execute form filling with retries
            success = fill_form_with_retries()
            return success
            
        except Exception as e:
            print(f"Error submitting form: {e}")
            return False
        finally:
            browser.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)