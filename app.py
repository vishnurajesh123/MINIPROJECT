from flask import Flask, request, jsonify, send_from_directory
from flask_bcrypt import Bcrypt
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
import requests  # For Mistral AI
import os
import time

# Set the environment variable correctly
os.environ["MISTRAL_API_KEY"] = "0SuooKNUYwXJsA56w9JejMDVXAPGztNE"

# Retrieve the API key correctly and print for debugging
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
print(f"Retrieved API Key: {MISTRAL_API_KEY}")  # Debug statement

# ✅ Initialize Flask App
app = Flask(__name__, static_folder="../frontend", static_url_path="/")
bcrypt = Bcrypt(app)
CORS(app)  # Allow cross-origin requests from the frontend

# ✅ MySQL Database Configuration
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "1234",  # Replace with your actual MySQL password
    "database": "project_management"
}

# ✅ Mistral AI Configuration
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

# ✅ Function to Get Database Connection
def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except Error as e:
        print(f"Database connection error: {e}")
        return None

# ✅ Signup Route
@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    qualification = data.get('qualification')  # For employees

    if not username or not password or not role:
        return jsonify({"message": "Missing required fields!"}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed!"}), 500

    cursor = conn.cursor()
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    if role == "manager":
        query = "INSERT INTO managers (username, password) VALUES (%s, %s)"
        values = (username, hashed_password)
    elif role == "employee":
        if not qualification:
            return jsonify({"message": "Qualification is required for employees!"}), 400
        query = "INSERT INTO employees (username, password, qualification) VALUES (%s, %s, %s)"
        values = (username, hashed_password, qualification)
    else:
        return jsonify({"message": "Invalid role!"}), 400

    try:
        cursor.execute(query, values)
        conn.commit()
        response = {"message": "User registered successfully!"}
    except mysql.connector.Error as err:
        response = {"message": f"Database error: {err}"}
    finally:
        cursor.close()
        conn.close()

    return jsonify(response)

# ✅ Login Route
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')

    if not username or not password or not role:
        return jsonify({"message": "Missing required fields!"}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed!"}), 500

    cursor = conn.cursor()
    if role == "manager":
        query = "SELECT password FROM managers WHERE username = %s"
        cursor.execute(query, (username,))
    elif role == "employee":
        query = "SELECT password, qualification FROM employees WHERE username = %s"
        cursor.execute(query, (username,))
    else:
        return jsonify({"message": "Invalid role!"}), 400

    result = cursor.fetchone()
    cursor.close()
    conn.close()

    if result and bcrypt.check_password_hash(result[0], password):
        response = {
            "message": "Login successful!",
            "redirect": f"/{role}_dashboard.html"
        }
        if role == "employee":
            response["qualification"] = result[1]  # Return qualification for employees
        return jsonify(response)
    else:
        return jsonify({"message": "Invalid credentials!"}), 401

# ✅ Fetch Employees
@app.route('/get_employees', methods=['GET'])
def get_employees():
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed!"}), 500

    cursor = conn.cursor(dictionary=True)
    query = "SELECT username, qualification FROM employees"
    cursor.execute(query)
    employees = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(employees)

def split_task_with_mistral(task_description, employees):
    """
    Uses Mistral AI to split a given task into subtasks based on employee qualifications.
    """
    try:
        if not MISTRAL_API_KEY:
            print("❌ ERROR: MISTRAL_API_KEY is missing.")
            return []

        print(f"📌 Sending task to Mistral AI: {task_description}")
        print(f"👥 Employees Data: {employees}")

        # Prepare employee info
        employee_info = [{"name": emp["username"], "qualification": emp["qualification"]} for emp in employees]

        # Make a request to Mistral AI API
        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "codestral-latest",  # Use the correct model name
            "messages": [
                {"role": "system", "content": "You are an AI assistant that splits tasks into subtasks and assigns them to employees based on qualifications."},
                {"role": "user", "content": f"Task: {task_description}. Employees: {employee_info}. Split and assign."}
            ]
        }

        response = requests.post(MISTRAL_API_URL, json=payload, headers=headers)

        print(f"📡 API Response Status: {response.status_code}")
        print(f"📜 API Response Content: {response.text}")

        if response.status_code == 429:  # Rate limit exceeded
            print("❌ Rate limit exceeded. Retrying after delay...")
            time.sleep(10)  # Wait before retrying
            response = requests.post(MISTRAL_API_URL, json=payload, headers=headers)

        if response.status_code != 200:
            print("❌ Mistral AI Error:", response.text)
            return []

        # Parse AI response
        ai_output = response.json()["choices"][0]["message"]["content"]
        print(f"✅ AI Output: {ai_output}")

        # Convert response into structured subtasks
        assigned_tasks = []
        for line in ai_output.split("\n"):
            if "→" in line:
                subtask, assigned_to = map(str.strip, line.split("→"))
                assigned_tasks.append({"subtask": subtask, "assigned_to": assigned_to})

        print(f"✅ Final Assigned Tasks: {assigned_tasks}")
        return assigned_tasks

    except Exception as e:
        print("❌ Error in Mistral AI request:", e)
        return []

# ✅ AI Task Splitting Route
@app.route("/ai_assign_task", methods=["POST"])
def ai_assign_task():
    data = request.json
    task_description = data.get("task")
    manager_username = data.get("manager")  # Assuming frontend passes the manager's username

    if not task_description:
        return jsonify({"error": "Task description is required"}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "Database connection failed"}), 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT username , qualification FROM employees")
    employees = cursor.fetchall()

    assigned_tasks = split_task_with_mistral(task_description, employees)

    # ✅ Insert assigned tasks into the `tasks` table
    try:
        for task in assigned_tasks:
            task_name = task_description  # Store original task description
            subtask_name = task["subtask"]
            assigned_employee = task["assigned_to"]
            subtask_description = task.get("description", "")  # Optional field
            priority = "medium"  # Default priority
            status = "pending"

            # ✅ Insert into `tasks` table
            cursor.execute("""
                INSERT INTO tasks (task, subtask, status, description, assigned_to, assigned_by, priority)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (task_name, subtask_name, status, subtask_description, assigned_employee, manager_username, priority))

        conn.commit()
        print("✅ Assigned tasks inserted into database successfully.")

    except Exception as e:
        conn.rollback()
        print("❌ ERROR inserting tasks into database:", e)

    cursor.close()
    conn.close()

    return jsonify({"subtasks": assigned_tasks})


def save_task_to_db(task_name, subtask, description, assigned_to, assigned_by, priority, deadline):
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password="1234",
        database="project_management"
    )
    cursor = connection.cursor()

    sql = """INSERT INTO tasks (task_name, subtask, description, assigned_to, assigned_by, status, deadline, priority)
             VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)"""
    
    values = (task_name, subtask, description, assigned_to, assigned_by, deadline, priority)

    cursor.execute(sql, values)
    connection.commit()
    connection.close()


# ✅ Serve Static Files (Frontend Pages)
@app.route('/')
def home():
    return send_from_directory("../frontend", "index.html")

@app.route('/manager_dashboard.html')
def manager_dashboard():
    return send_from_directory("../frontend", "manager_dashboard.html")

@app.route('/employee_dashboard.html')
def employee_dashboard():
    return send_from_directory("../frontend", "employee_dashboard.html")

@app.route('/<path:filename>')
def serve_static_files(filename):
    return send_from_directory("../frontend", filename)

# ✅ Run the Flask Server
if __name__ == '__main__':
     app.run(debug=True)
