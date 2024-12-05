from flask import Flask, request, jsonify
from flask_cors import CORS
import fitz  # PyMuPDF
from utils import extract_pdf_details,extract_pdf_details_android
from pymongo import MongoClient
import os
import tempfile
import urllib.parse
from collections import defaultdict
from datetime import datetime
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from bson.objectid import ObjectId
from io import BytesIO
from pytube import YouTube
import instaloader

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# MongoDB setup
username = "satyaranjanparida038"
password = "te8aFRXE6m4SqY7y"

# URL encode the username and password
encoded_username = urllib.parse.quote_plus(username)
encoded_password = urllib.parse.quote_plus(password)

# Construct the MongoDB URI
MONGO_URI = f"mongodb+srv://{encoded_username}:{encoded_password}@cluster0.rzqy9ul.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['ExpenseTrackerDB']  # Database name
collection = db['YearlyData']    # Collection name
current_month_collection = db['CurrentMonthTransactions']
user_collection = db['User'] #user collection
signup_collection = db['SignUp'] #signup collection
friendship_data_collection = db["friendship"] #friendship data
category_mapping_collection = db['CategoryMapping']  # Collection to store party-category mappings


def delete_all_data():
    try:
        result = signup_collection.delete_many({})
        print(f"Deleted {result.deleted_count} documents from the SignUp collection.")
    except Exception as e:
        print(f"An error occurred: {e}")
        
@app.route('/download/youtube', methods=['POST'])
def download_youtube_video():
    try:
        data = request.json
        url = data.get('url')
        if not url:
            return jsonify({"error": "URL is required"}), 400
 
        yt = YouTube(url)
        stream = yt.streams.filter(progressive=True, file_extension='mp4').first()
 
        if not stream:
            return jsonify({"error": "No valid stream found"}), 400
 
        # Download the video to memory
        file_buffer = BytesIO()
        stream.stream_to_buffer(file_buffer)
        file_buffer.seek(0)
 
        return send_file(file_buffer, as_attachment=True, download_name=f"{yt.title}.mp4", mimetype='video/mp4')
 
    except Exception as e:
        return jsonify({"error": str(e)}), 500
 
 
@app.route('/download/instagram', methods=['POST'])
def download_instagram_video():
    try:
        data = request.json
        url = data.get('url')
        if not url:
            return jsonify({"error": "URL is required"}), 400
 
        loader = instaloader.Instaloader()
        shortcode = url.split("/")[-2]
 
        # Download the Instagram post to memory
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        if not post.is_video:
            return jsonify({"error": "The provided link is not a video"}), 400
 
        file_buffer = BytesIO()
        loader.download_post(post, target=None)
        downloaded_file_path = loader.dirname_pattern  # Use in-memory storage
 
        # Read the file into a buffer
        with open(downloaded_file_path, 'rb') as f:
            file_buffer.write(f.read())
        file_buffer.seek(0)
 
        return send_file(file_buffer, as_attachment=True, download_name=f"{shortcode}.mp4", mimetype='video/mp4')
 
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get-password', methods=['POST'])
def get_password():
    data = request.json
    email = data.get("email")

    if not email:
        return jsonify({"message": "Email is required"}), 400

    # Search for the user in the database
    user = user_collection.find_one({"userName": email})
    if user:
        # Assuming the password is stored in plaintext (not recommended)
        password = user.get("password")
        if password:
            return jsonify({"email": email, "password": password}), 200
        else:
            return jsonify({"message": "Password not found for the given email"}), 404

    return jsonify({"message": "No user found with the provided email address"}), 404

def test_connection():
    try:
        client = MongoClient(MONGO_URI)
        print("Connected to MongoDB successfully!")
    except Exception as e:
        print("Error connecting to MongoDB:", e)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    password = request.form.get('password', '')  # Optional password input
    user_name = request.form.get('userName')  # Get the username from the form data
    device = request.form.get("device")

    if not user_name:
        return jsonify({"error": "Username is required"}), 400

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Create a temporary directory and save the file there
    with tempfile.TemporaryDirectory() as tmpdirname:
        file_path = os.path.join(tmpdirname, file.filename)
        file.save(file_path)

        # Extract PDF details (assuming extract_pdf_details is already implemented)
        if device == "ios":
            data = extract_pdf_details(file_path, password)
        else:
            data = extract_pdf_details_android(file_path, password)

        # Aggregating amounts by month, year, and transaction type
        aggregated_amounts = defaultdict(lambda: defaultdict(float))
        current_month_transactions = []

        for transaction in data['transactions']:
            date_str = transaction.get('date')
            transaction_type = transaction.get('transaction_type')
            amount_str = transaction.get('amount')
            party = transaction.get('party')

            if not all([date_str, transaction_type, amount_str, party]):
                print(f"Incomplete transaction data: {transaction}")
                continue
            

            # Parse date and amount
            date = datetime.strptime(date_str, '%b %d, %Y')
            amount = float(amount_str.replace("INR ", "").replace(",", ""))

            # Fetch the category from the category mapping
            mapping = category_mapping_collection.find_one({"party": party})
            category = mapping['category'] if mapping else None

            # Create a key for month and year
            year_month_key = f"{date.year}-{date.strftime('%B').upper()}"

            # Aggregate amount
            aggregated_amounts[year_month_key][transaction_type] += amount

            

            # Collect current month's transactions
            current_month = datetime.now().strftime('%B').upper()
            if date.strftime('%B').upper() == current_month:
                # Check for duplicates before saving
                duplicate = current_month_collection.find_one({
                    "userName": user_name,
                    "date": date_str,
                    "amount": amount,
                    "transactionType": transaction_type
                })
                if not duplicate:
                    current_month_transactions.append({
                        "userName": user_name,
                        "date": date_str,
                        "amount": amount,
                        "transactionType": transaction_type,
                        "party": party,
                        "category": category  # Assign the fetched category
                    })

        # Save current month's transactions to a separate collection
        if current_month_transactions:
            current_month_collection.insert_many(current_month_transactions)

        # Save or update the aggregated amounts to MongoDB
        for year_month, type_amounts in aggregated_amounts.items():
            year, month = year_month.split('-')

            for transaction_type, amount in type_amounts.items():
                existing_transaction = collection.find_one({
                    "userName": user_name,
                    "month": month,
                    "year": year,
                    "transactionType": transaction_type
                })

                if existing_transaction:
                    collection.update_one(
                        {"_id": existing_transaction["_id"]},
                        {"$set": {"amount": amount}}
                    )
                else:
                    collection.insert_one({
                        "userName": user_name,
                        "month": month,
                        "year": year,
                        "amount": amount,
                        "transactionType": transaction_type
                    })

    return jsonify(data), 201



@app.route('/androidUpload', methods=['POST'])
def uploadAndroid_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    password = request.form.get('password', '')  # Optional password input
    user_name = request.form.get('userName')  # Get the username from the form data

    if not user_name:
        return jsonify({"error": "Username is required"}), 400

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    # Create a temporary directory and save the file there
    with tempfile.TemporaryDirectory() as tmpdirname:
        file_path = os.path.join(tmpdirname, file.filename)
        file.save(file_path)

        # Extract PDF details (assuming extract_pdf_details is already implemented)
        data = extract_pdf_details_android(file_path, password)
    return jsonify(data) , 200


@app.route('/iosUpload', methods=['POST'])
def uploadIos_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    password = request.form.get('password', '')  # Optional password input
    user_name = request.form.get('userName')  # Get the username from the form data

    if not user_name:
        return jsonify({"error": "Username is required"}), 400

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    # Create a temporary directory and save the file there
    with tempfile.TemporaryDirectory() as tmpdirname:
        file_path = os.path.join(tmpdirname, file.filename)
        file.save(file_path)

        # Extract PDF details (assuming extract_pdf_details is already implemented)
        data = extract_pdf_details(file_path, password)
    return jsonify(data) , 200
# Endpoint to retrieve data by username
@app.route('/get-data/<username>', methods=['GET'])
def get_data(username):
    try:
        result = list(collection.find({"userName": username}, {"_id": 0}))
        if not result:
            return jsonify({"message": "No data found for this user"}), 404
        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Endpoint to delete all data for a specific username
@app.route('/delete-data/<username>', methods=['DELETE'])
def delete_data(username):
    try:
        # Delete all documents that match the given username
        delete_result = current_month_collection.delete_many({"userName": username})

        if delete_result.deleted_count == 0:
            return jsonify({"message": "No data found for this user"}), 404
        return jsonify({"message": f"Deleted {delete_result.deleted_count} record(s) for user {username}"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

from bson import ObjectId

@app.route('/get-current-month-transactions/<username>', methods=['GET'])
def get_current_month_transactions(username):
    try:
        current_month = datetime.now().strftime('%b')  # 'Aug' format
        current_year = datetime.now().year

        # Adjust the regex to match the date format "Aug 01, 2024"
        date_regex = f"^{current_month}.*{current_year}$"

        # Include the _id field in the result and convert ObjectId to string
        result = list(current_month_collection.find({
            "userName": username,
            "date": {"$regex": date_regex}
        }, {"userName": 1, "date": 1, "amount": 1, "transactionType": 1, "party": 1, "category": 1}))

        # Convert _id to string for JSON serialization
        for item in result:
            item['_id'] = str(item['_id'])

        if not result:
            return jsonify({"message": "No data found for the current month"}), 404
        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500



def delete_previous_month_data():
    previous_month = (datetime.now() - timedelta(days=30)).strftime('%B').upper()
    previous_year = (datetime.now() - timedelta(days=30)).year
    print("scheduler is running on server"); 

    # Delete data for the previous month
    result = current_month_collection.delete_many({
        "date": {"$regex": f"{previous_month} {previous_year}"}
    })
    print(f"Deleted {result.deleted_count} records from the previous month.")

scheduler = BackgroundScheduler()
scheduler.add_job(delete_previous_month_data, 'cron', day=1, hour=0, minute=0)
scheduler.add_job(delete_all_data, 'cron', minute='*/10')


@app.route('/delete-completed-month', methods=['POST'])
def delete_completed_month():
    try:
        user_name = request.json.get('userName')

        if not user_name:
            return jsonify({"error": "Username is required"}), 400

        # Delete data for the completed month
        result = current_month_collection.delete_many({
            "userName": user_name
        })

        return jsonify({"message": f"{result.deleted_count} transactions deleted."}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update-category/<transaction_id>', methods=['PUT'])
def update_category(transaction_id):
    try:
        # Get the new category and fetch the transaction
        new_category = request.json.get('category')
        if not new_category:
            return jsonify({"error": "Category is required"}), 400

        # Convert transaction_id to ObjectId
        transaction_id = ObjectId(transaction_id)

        # Find the transaction by _id
        transaction = current_month_collection.find_one({"_id": transaction_id})
        if not transaction:
            return jsonify({"error": "Transaction not found"}), 404

        # Update the category of the specific transaction
        current_month_collection.update_one(
            {"_id": transaction_id},
            {"$set": {"category": new_category}}
        )

        # Update the category mapping for the party
        party = transaction.get('party')
        if not party:
            return jsonify({"error": "Party not found in the transaction"}), 400

        category_mapping_collection.update_one(
            {"party": party},
            {"$set": {"category": new_category}},
            upsert=True
        )

        # Update all existing transactions for this party
        current_month_collection.update_many(
            {"party": party},
            {"$set": {"category": new_category}}
        )
        collection.update_many(
            {"party": party},
            {"$set": {"category": new_category}}
        )

        return jsonify({"message": "Category updated successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/get-category-totals/<username>', methods=['GET'])
def get_category_totals(username):
    try:
        current_month = datetime.now().strftime('%b')  # 'Aug' format
        current_year = datetime.now().year

        # Adjust the regex to match the date format "Aug 01, 2024"
        date_regex = f"^{current_month}.*{current_year}$"

        # Aggregate total amounts by category for the current month
        pipeline = [
            {
                "$match": {
                    "userName": username,
                    "date": {"$regex": date_regex}
                }
            },
            {
                "$group": {
                    "_id": "$category",
                    "totalAmount": {"$sum": "$amount"}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "category": "$_id",
                    "totalAmount": 1
                }
            }
        ]

        result = list(current_month_collection.aggregate(pipeline))

        if not result:
            return jsonify({"message": "No data found for the current month"}), 404
        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def generate_otp(length=4):
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

def send_email(to_email, subject, body):
    from_email = "moviesearch358@gmail.com"
    password = "slfh dwda igvx kzra"

    # Set up the MIME
    message = MIMEMultipart()
    message['From'] = from_email
    message['To'] = to_email
    message['Subject'] = subject
    message.attach(MIMEText(body, 'html'))

    # Send email
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(from_email, password)
            server.sendmail(from_email, to_email, message.as_string())
        return "Email sent successfully"
    except Exception as e:
        return f"Failed to send email: {str(e)}"

@app.route('/sendOtp', methods=['POST'])
def sign_up():
    data = request.json
    user = user_collection.find_one({"userName": data['userName'], "password": data['password']})

    if user:
        return jsonify({"message": "User already exists"}), 403

    otp = generate_otp()
    emailBody = generate_email_body(otp) ; 
    send_email_result = send_email(data['userName'], "Your OTP for Verification", emailBody)

    if "Failed" in send_email_result:
        return jsonify({"message": send_email_result}), 500

    signup_collection.insert_one({
        "userName": data['userName'],
        "otp": otp
    })

    return jsonify({"message": "OTP sent successfully"}), 200

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    user = user_collection.find_one({"userName": data['userName'], "password": data['password']})

    if user:
        return jsonify({"message": "Login successful"}), 200
    return jsonify({"message": "User authentication failed, Please verify your credentials"}), 401

@app.route('/verifyOtp', methods=['POST'])
def verify_otp():
    otp = request.args.get('otp')
    data = request.json
    signup = signup_collection.find_one({"userName": data['userName']})
    

    if signup and str(signup['otp']) == otp:
        user_collection.insert_one({
            "userName": data['userName'],
            "password": data['password']
        })
        signup_collection.delete_one({"_id": signup['_id']})
        return jsonify({"message": "Sign up successfully"}), 200
    return jsonify({"message": "SignUp Unsuccessful"}), 400

@app.route('/sendEmail/<email>', methods=['POST'])
def send_email_route(email):
    otp = generate_otp()
    send_email(email, "Your OTP for Verification", f"Your OTP is: {otp}")
    return "Email sent successfully"

@app.route('/welcome', methods=['GET'])
def welcome():
    return "Welcome to the practice application project"

@app.route('/HelloWorld/<userName>', methods=['GET'])
def hello_world(userName):
    return f"Hello {userName}, Welcome to my practice application"

def generate_email_body(otp):
    return f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2>Your OTP for Verification</h2>
            <p>Dear User,</p>
            <p>Your One-Time Password (OTP) for verification is:</p>
            <h1 style="color: #0066cc;">{otp}</h1>
            <p>Please use this OTP to complete your verification. Do not share this OTP with anyone.</p>
            <br>
            <p>Thank you,</p>
            <p>Expense Tracker Admin</p>
        </body>
    </html>
    """

@app.route('/get-unique-usernames', methods=['GET'])
def get_unique_usernames():
    usernames = user_collection.distinct("userName")
    return jsonify({"uniqueUsernames": usernames})

@app.route('/update-password', methods=['POST'])
def update_password():
    data = request.json
    username = data.get('userName')
    new_password = data.get('newPassword')
    
    if not username or not new_password:
        return jsonify({"error": "Missing userName or newPassword"}), 400
    
    result = user_collection.update_one(
        {"userName": username},
        {"$set": {"password": new_password}}
    )
    
    if result.matched_count > 0:
        return jsonify({"message": "Password updated successfully"}), 200
    else:
        return jsonify({"error": "User not found"}), 404


def send_daily_expenses():
    today = datetime.today().strftime('%Y-%m-%d')
    expenses = list(current_month_collection.find({"date": {"$regex": today}}))
    
    # Implement your notification/email logic here
    print(f"Sending daily expenses for {today}: {expenses}")
scheduler.add_job(send_daily_expenses, 'cron', hour=21, minute=30)


# friend ship apis 
friendship_codes_collection = db["friendship_codes"]

def generate_code():
    return random.randint(10000, 99999)

@app.route('/generate_code', methods=['POST'])
def generate_friendship_code():
    user_id = request.json.get("user_id")
    code = generate_code()
    expiration_time = datetime.utcnow() + timedelta(minutes=10)
    
    friendship_codes_collection.insert_one({
        "user_id": user_id,
        "code": code,
        "expires_at": expiration_time
    })
    
    return jsonify({"code": code}), 200

@app.route('/add_friend', methods=['POST'])
def add_friend():
    user_id = request.json.get("user_id")
    code = request.json.get("code")
    
    print("Received code: ", code, "Type:", type(code))
    print("Received user_id: ", user_id)

    # Convert the code to an integer if it’s stored as an integer in the database
    try:
        code = int(code)
    except ValueError:
        return jsonify({"error": "Code should be a valid number"}), 400

    print("Converted code: ", code, "Type:", type(code))

    # Find the code entry in the friendship_codes_collection
    code_entry = friendship_codes_collection.find_one({"code": code})
    
    if not code_entry:
        print("Invalid code or code not found in database.")
        return jsonify({"error": "Invalid code"}), 400
    
    if code_entry["expires_at"] < datetime.utcnow():
        return jsonify({"error": "Code expired"}), 400
    
    friend_id = code_entry["user_id"]
    
    if user_id == friend_id:
        return jsonify({"error": "You cannot add yourself as a friend"}), 400
    
    # Store the friendship data in the friendship_data_collection
    friendship_data_collection.insert_one({
        "user_name": user_id,
        "friend_name": friend_id,
        "created_at": datetime.utcnow()
    })

    friendship_data_collection.insert_one({
        "user_name": friend_id,
        "friend_name": user_id,
        "created_at": datetime.utcnow()
    })

    # Optionally, also update the user_collection if you want to maintain friend_ids there
    user_collection.update_one(
        {"_id": user_id},
        {"$addToSet": {"friend_ids": friend_id}}
    )
    user_collection.update_one(
        {"_id": friend_id},
        {"$addToSet": {"friend_ids": user_id}}
    )
    
    # Remove the used code from the friendship_codes_collection
    friendship_codes_collection.delete_one({"code": code})
    
    return jsonify({"message": "Friend added successfully"}), 200

@app.route('/getFriendsByUserName', methods=['GET'])
def get_friends_by_user_name():
    user_name = request.args.get("user_name")
    
    if not user_name:
        return jsonify({"error": "User name is required"}), 400
    
    # Find all friendships where user_name matches
    friendships = friendship_data_collection.find({"user_name": user_name})
    
    # Extract friend names from the result
    friend_names = [friendship["friend_name"] for friendship in friendships]
    
    if not friend_names:
        return jsonify({"message": "No friends found for the given user name"}), 404
    
    return jsonify({"friend_names": friend_names}), 200



# Insert a test document to ensure the collection is created



scheduler.start() 


if __name__ == '__main__':
     
    app.run(host='0.0.0.0', port=5000)
