from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()
uri = os.getenv("MONGO_URI")
print("MONGO_URI:", uri)
uri='mongodb+srv://akash:9934489812Aa@web-jee.21cjl50.mongodb.net/?retryWrites=true&w=majority'

try:
    client = MongoClient(uri)
    print("✅ Databases:", client.list_database_names())
except Exception as e:
    print("❌ Connection failed:", e)
