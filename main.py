from fastapi import FastAPI, Request
from pydantic import BaseModel
from playwright.sync_api import sync_playwright
import uvicorn

app = FastAPI()

class LeadData(BaseModel):
    first_name: str
    last_name: str
    email: str
    custom_field: str

def submit_form(first_name, last_name, email, custom_field):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://api.leadconnectorhq.com/widget/form/UQVFhuQiNCfdJTydbFrm")
        page.fill('input[name="first_name"]', first_name)
        page.fill('input[name="last_name"]', last_name)
        page.fill('input[name="email"]', email)
        page.fill('input[name="yC389AjWtdl4nv9GkvZM"]', custom_field)
        page.click('button[type="submit"]')
        page.wait_for_timeout(2000)
        browser.close()
        return True

@app.post("/submit-lead")
def create_lead(data: LeadData):
    # Optional: Add input validation, spam checking, etc. here
    submit_form(
        data.first_name,
        data.last_name,
        data.email,
        data.custom_field
    )
    return {"status": "submitted"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
