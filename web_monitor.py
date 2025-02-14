import logging
import os
from fastapi import FastAPI, HTTPException
import asyncio
import psycopg2
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import smtplib

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more detail
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI with explicit port binding
port = int(os.getenv("PORT", 10000))
app = FastAPI(title="Website Monitor")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration with debug logging
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT")
}

# Log DB config (with password hidden)
debug_config = DB_CONFIG.copy()
debug_config["password"] = "****" if debug_config["password"] else None
logger.debug(f"Database configuration: {debug_config}")

async def get_websites_from_db():
    """Fetch websites to monitor from database."""
    try:
        logger.debug(f"Attempting database connection to {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        logger.debug(f"Database: {DB_CONFIG['dbname']}, User: {DB_CONFIG['user']}")
        
        conn = psycopg2.connect(**DB_CONFIG)
        logger.info("✅ Database connection successful")
        
        cur = conn.cursor()
        logger.debug("Executing query: SELECT url, email, phone FROM wix_submissions.websites")
        cur.execute("SELECT url, email, phone FROM wix_submissions.websites;")
        records = cur.fetchall()
        
        logger.info(f"📋 Found {len(records)} websites to monitor")
        logger.debug(f"First few records: {records[:3] if records else 'No records'}")
        
        cur.close()
        conn.close()
        return records
        
    except psycopg2.OperationalError as e:
        logger.error(f"❌ Database connection failed: {e}")
        logger.error(f"Connection details: {debug_config}")
        return []
    except psycopg2.Error as e:
        logger.error(f"❌ Database error: {e.pgerror if hasattr(e, 'pgerror') else str(e)}")
        logger.error(f"Error code: {e.pgcode if hasattr(e, 'pgcode') else 'Unknown'}")
        return []
    except Exception as e:
        logger.error(f"❌ Unexpected error: {str(e)}")
        logger.exception("Full traceback:")
        return []

# ... rest of your code ...

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on port {port}")
    logger.debug("Database configuration loaded:")
    logger.debug(f"Host: {DB_CONFIG['host']}")
    logger.debug(f"Port: {DB_CONFIG['port']}")
    logger.debug(f"Database: {DB_CONFIG['dbname']}")
    logger.debug(f"User: {DB_CONFIG['user']}")
    uvicorn.run(
        "web_monitor:app",
        host="0.0.0.0",
        port=port,
        reload=False
    ) 
