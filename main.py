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
        # 1. Go to your public web page
        page.goto("https://camrenhall.github.io/roth-davies-form-public/")
        # 2. Wait for the iframe to load
        page.wait_for_selector('iframe#inline-UQVFhuQiNCfdJTydbFrm')
        # 3. Switch to iframe context
        frame = page.frame_locator('iframe#inline-UQVFhuQiNCfdJTydbFrm').frame()
        # 4. Fill out fields inside the iframe (selectors are GHL field names)
        frame.fill('input[name="first_name"]', first_name)
        frame.fill('input[name="last_name"]', last_name)
        frame.fill('input[name="email"]', email)
        # Phone is optional
        if phone:
            frame.fill('input[name="phone"]', phone)
        # "Tell Us About Your Case" - the field name comes from inspecting the actual form
        frame.fill('textarea[name="yC389AjWtdl4nv9GkvZM"]', about_case)
        # 5. Click submit (button selector may need to be adjusted after inspecting actual form)
        frame.click('button[type="submit"]')
        # 6. Optionally wait for a confirmation or result
        page.wait_for_timeout(2000)
        browser.close()
        return True

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
