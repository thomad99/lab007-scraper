import logging
import os
from fastapi import FastAPI, HTTPException
import asyncio
import psycopg2
import requests
import smtplib
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI with explicit port binding
port = int(os.getenv("PORT", 10000))  # Render will provide PORT env variable
app = FastAPI(title="Website Monitor")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your actual domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add a health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "port": port}

# Database configuration
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT")
}

# Email configuration
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "dave@LoveSailing.ai")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.ionos.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# Add these global variables to track monitoring status
monitoring_status = {
    "is_running": False,
    "started_at": None,
    "current_cycle": 0,
    "last_check": None
}

async def get_websites_from_db():
    """Fetch websites to monitor from database."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT url, email, phone FROM websites;")
        records = cur.fetchall()
        cur.close()
        conn.close()
        logger.info(f"📋 Found {len(records)} websites to monitor")
        return records
    except Exception as e:
        logger.error(f"❌ Database error fetching websites: {e}")
        return []

async def scrape_website(url):
    """Scrape website content."""
    try:
        logger.info(f"🌍 Scraping {url}")
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            content = soup.get_text()
            logger.info(f"✅ Successfully scraped {url} ({len(content)} chars)")
            return content
        else:
            logger.error(f"❌ Failed to scrape {url}: Status {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"❌ Error scraping {url}: {e}")
        return None

def save_scrape_to_db(url, content):
    """Save scraped content to database with timestamp."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        timestamp = datetime.now()
        cur.execute(
            "INSERT INTO website_snapshots (url, content, scraped_at) VALUES (%s, %s, %s)",
            (url, content, timestamp)
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"💾 Saved snapshot for {url}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to save snapshot for {url}: {e}")
        return False

def get_last_snapshot(url):
    """Get the most recent snapshot for a URL."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "SELECT content FROM website_snapshots WHERE url = %s ORDER BY scraped_at DESC LIMIT 1",
            (url,)
        )
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"❌ Failed to get last snapshot for {url}: {e}")
        return None

async def send_change_alert(email, url, phone=None):
    """Send email alert when change is detected."""
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = email
        msg["Subject"] = f"🔔 Website Change Detected: {url}"
        
        body = f"""
A change has been detected on the website: {url}

Time of detection: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

You can view the website at: {url}

This is an automated alert from your website monitoring service.
        """
        
        msg.attach(MIMEText(body, "plain"))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, email, msg.as_string())
        server.quit()
        
        logger.info(f"📧 Change alert sent to {email} for {url}")
    except Exception as e:
        logger.error(f"❌ Failed to send alert email: {e}")

async def monitor_websites():
    """Main monitoring loop."""
    try:
        monitoring_status["is_running"] = True
        monitoring_status["started_at"] = datetime.now()
        monitoring_status["current_cycle"] = 0

        cycle = 0
        while cycle < 10:
            cycle += 1
            monitoring_status["current_cycle"] = cycle
            logger.info(f"🔄 Starting monitoring cycle {cycle}/10")
            
            websites = await get_websites_from_db()
            if not websites:
                logger.warning("⚠️ No websites found to monitor")
                break
            
            for url, email, phone in websites:
                if not monitoring_status["is_running"]:
                    logger.info("🛑 Monitoring stopped by user")
                    return

                logger.info(f"📊 Checking {url}")
                monitoring_status["last_check"] = datetime.now()
                
                current_content = await scrape_website(url)
                if not current_content:
                    continue
                    
                save_scrape_to_db(url, current_content)
                previous_content = get_last_snapshot(url)
                
                if previous_content and previous_content.strip() != current_content.strip():
                    logger.info(f"🔔 Change detected on {url}")
                    await send_change_alert(email, url, phone)
                
                logger.info(f"⏳ Waiting 60 seconds before next check...")
                await asyncio.sleep(60)
            
            logger.info(f"✅ Completed cycle {cycle}/10")
        
        logger.info("🏁 Monitoring completed after 10 cycles")
    finally:
        monitoring_status["is_running"] = False

@app.get("/")
async def root():
    return {
        "status": "online",
        "endpoints": {
            "start": "/start - Start monitoring",
            "stop": "/stop - Stop monitoring",
            "status": "/status - Check monitoring status"
        },
        "version": "1.0"
    }

@app.get("/start", response_class=JSONResponse)
async def start_monitoring():
    """Start the monitoring process."""
    try:
        if monitoring_status["is_running"]:
            return JSONResponse({
                "message": "Monitoring is already running",
                "started_at": monitoring_status["started_at"].isoformat() if monitoring_status["started_at"] else None,
                "current_cycle": monitoring_status["current_cycle"]
            })
        
        logger.info("🚀 Starting website monitoring")
        asyncio.create_task(monitor_websites())
        return JSONResponse({
            "message": "Monitoring started for 10 cycles",
            "status": "success"
        })
    except Exception as e:
        logger.error(f"Failed to start monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stop", response_class=JSONResponse)
async def stop_monitoring():
    """Stop the monitoring process."""
    try:
        if not monitoring_status["is_running"]:
            return JSONResponse({"message": "Monitoring is not running"})
        
        monitoring_status["is_running"] = False
        return JSONResponse({
            "message": "Stopping monitoring process",
            "status": "success"
        })
    except Exception as e:
        logger.error(f"Failed to stop monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status", response_class=JSONResponse)
async def get_monitoring_status():
    """Get current monitoring status."""
    try:
        return JSONResponse({
            "is_running": monitoring_status["is_running"],
            "started_at": monitoring_status["started_at"].isoformat() if monitoring_status["started_at"] else None,
            "current_cycle": monitoring_status["current_cycle"],
            "last_check": monitoring_status["last_check"].isoformat() if monitoring_status["last_check"] else None
        })
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print(f"Starting server on port {port}")
    uvicorn.run(
        "web_monitor:app",  # use string reference to app
        host="0.0.0.0",
        port=port,
        reload=False
    )
