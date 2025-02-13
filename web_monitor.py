from fastapi import FastAPI, BackgroundTasks
import asyncio
import psycopg2
import requests
import smtplib
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = FastAPI()

import os

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT")
}

EMAIL_SENDER = "dave@LoveSailing.ai"
EMAIL_PASSWORD = "Bugvan98!Crocket3"
SMTP_SERVER = "smtp.ionos.com"
SMTP_PORT = 587

async def get_websites_from_db():
    """Fetch URL, email, and phone from the database."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT url, email, phone FROM websites;")
    records = cur.fetchall()
    conn.close()
    return records

async def scrape_website(url):
    """Scrapes the website and extracts text content."""
    print(f"🌍 Scraping: {url}...")  # Debug log
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            scraped_content = soup.get_text()
            print(f"✅ Successfully scraped {url} ({len(scraped_content)} characters)")
            return scraped_content
        else:
            print(f"❌ Failed to scrape {url} - Status Code: {response.status_code}")
            return None
    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")
        return None


async def send_email_alert(to_email, url):
    """Sends an email when a website change is detected."""
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = to_email
        msg["Subject"] = f"Website Change Alert: {url}"
        msg.attach(MIMEText(f"The content of {url} has changed!", "plain"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, to_email, msg.as_string())
        server.quit()

        print(f"📧 Email Alert Sent to {to_email} for {url}")
    except Exception as e:
        print(f"❌ Email Error: {e}")

async def monitor_websites():
    """Runs the website monitoring loop for 10 cycles."""
    websites = await get_websites_from_db()
    website_data = {}

    for _ in range(10):  # Run 10 iterations
        for url, email, phone in websites:
            new_content = await scrape_website(url)

            if new_content:
                # ✅ Save scraped data to database
                save_scraped_data(url, new_content)  # NEW LINE

                if url in website_data:
                    old_content = website_data[url]
                    if old_content.strip() != new_content.strip():
                        print(f"🔄 Change detected at {url}")
                        await send_email_alert(email, url)
                else:
                    print(f"✅ First scan of {url}")

                website_data[url] = new_content

        print("⏳ Waiting 1 minute before next scan...")
        await asyncio.sleep(60)  # Async wait for 1 minute

    print("✅ Monitoring completed after 10 cycles.")

@app.get("/")
async def read_root():
    return {"message": "FastAPI is running!"}

@app.get("/start-monitoring")
async def start_monitoring(background_tasks: BackgroundTasks):
    """Starts the monitoring in the background."""
    background_tasks.add_task(monitor_websites)
    return {"message": "Monitoring started and will run for 10 cycles."}



def save_scraped_data(url, content):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO website_snapshots (url, scraped_content) VALUES (%s, %s);",
        (url, content)
    )
    conn.commit()
    conn.close()

