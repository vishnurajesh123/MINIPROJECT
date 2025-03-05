import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG  # Or define DB_CONFIG here
from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()
def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Database connection error: {e}")
        return None

def register_user(username, password, role):
    conn = get_db_connection()
    if not conn:
        return
    cursor = conn.cursor()
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    if role == "manager":
        query = "INSERT INTO managers (username, password) VALUES (%s, %s)"
    elif role == "employee":
        query = "INSERT INTO employees (username, password) VALUES (%s, %s)"
    else:
        print("Invalid role!")
        return
    try:
        cursor.execute(query, (username, hashed_password))
        conn.commit()
        print(f"User {username} registered successfully as {role}!")
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
    finally:
        cursor.close()
        conn.close()

# Example usage:
register_user("admin", "admin123", "manager")
register_user("john", "john123", "employee")
