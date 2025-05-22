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
        page.goto("https://camrenhall.github.io/roth-davies-form-public/")
        page.wait_for_selector('iframe#inline-UQVFhuQiNCfdJTydbFrm')

        # Grab the iframe again AFTER the page/iframe is stable
        def get_live_form_frame():
            # Wait for the form input to appear in ANY child frame
            for _ in range(30):  # retry up to 6 seconds
                for f in page.frames:
                    try:
                        if f.url and "leadconnectorhq.com/widget/form/UQVFhuQiNCfdJTydbFrm" in f.url:
                            # Try to see if our input is available
                            if f.query_selector('input[name="first_name"]'):
                                return f
                    except Exception:
                        pass
                page.wait_for_timeout(200)
            raise Exception("Could not find live form frame with inputs.")

        frame = get_live_form_frame()
        frame.fill('input[name="first_name"]', first_name)
        frame.fill('input[name="last_name"]', last_name)
        frame.fill('input[name="email"]', email)
        if phone:
            frame.fill('input[name="phone"]', phone)
        frame.fill('textarea[name="yC389AjWtdl4nv9GkvZM"]', about_case)
        frame.click('button[type="submit"]')
        page.wait_for_timeout(2000)
        browser.close()
        return True



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
