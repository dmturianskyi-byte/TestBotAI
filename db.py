import os
import psycopg2

from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT"),
    database=os.getenv("PG_DATABASE"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
)

register_vector(conn)


def get_cursor():
    return conn.cursor()