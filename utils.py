import fitz  # PyMuPDF
import re

def extract_pdf_details(file_path, password=''):
    # Open the PDF file
    doc = fitz.open(file_path)

    # Attempt to unlock the document if it's password-protected
    if doc.needs_pass:
        if not doc.authenticate(password):
            return {"error": "Invalid password or unable to unlock PDF."}

    details = []

    # Regular expressions to match data
    date_pattern = re.compile(r'\b[A-Za-z]{3} \d{2}, \d{4}\b')  # Matches dates like "Nov 30, 2024"
    amount_pattern = re.compile(r'INR [\d,]+(?:\.\d{1,2})?')  # Matches "INR 19000.00"
    transaction_type_pattern = re.compile(r'\b(Debit|Credit)\b')  # Matches "Debit" or "Credit"
    party_pattern = re.compile(r'(Paid to|Received from|Paid -|Bill paid -|Payment|Refund Received -) (.+)')
 # Matches "Paid to ..." or "Received from ..."

    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        lines = text.splitlines()

        current_transaction = {}
        in_transaction_block = False

        for line in lines:
            # Match transaction date
            date_match = date_pattern.search(line)
            if date_match:
                if current_transaction:
                    # Save the previous transaction if complete
                    if 'date' in current_transaction and 'amount' in current_transaction:
                        details.append(current_transaction)
                    current_transaction = {}  # Start a new transaction

                current_transaction['date'] = date_match.group()
                in_transaction_block = True

            # Match transaction type
            type_match = transaction_type_pattern.search(line)
            if in_transaction_block and type_match:
                current_transaction['transaction_type'] = type_match.group()

            # Match party (Paid to or Received from)
            party_match = party_pattern.search(line)
            if in_transaction_block and party_match:
                current_transaction['party'] = party_match.group(2).strip()

            # Match amount
            amount_match = amount_pattern.search(line)
            if in_transaction_block and amount_match:
                amount_str = amount_match.group()
                formatted_amount = amount_str.replace('INR', '').replace(',', '').strip()
                current_transaction['amount'] = formatted_amount

            # If all fields are captured, finalize the transaction
            if (
                'date' in current_transaction
                and 'transaction_type' in current_transaction
                and 'party' in current_transaction
                and 'amount' in current_transaction
            ):
                details.append(current_transaction)
                current_transaction = {}  # Reset for the next transaction
                in_transaction_block = False

        # Add the last transaction if it wasn't saved
        if current_transaction and 'amount' in current_transaction:
            details.append(current_transaction)

    return {
        "transactions": details
    }



def extract_pdf_details_android(file_path, password=''):
    # Open the PDF file
    doc = fitz.open(file_path)

    # Attempt to unlock the document if it's password-protected
    if doc.needs_pass:
        if not doc.authenticate(password):
            return {"error": "Invalid password or unable to unlock PDF."}

    details = []

    # Regular expressions to match the data
    date_pattern = re.compile(r'\b[A-Za-z]{3} \d{2}, \d{4}\b')
    amount_pattern = re.compile(r'₹[\d,]+(\.\d{1,2})?')  # Matches amount with ₹ symbol and handles commas

    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        lines = text.splitlines()

        current_detail = {}

        for line in lines:
            # Extract Date
            date_match = date_pattern.search(line)
            if date_match:
                current_detail['date'] = date_match.group()

            # Extract "Paid to" or "Received from" information
            if "Paid to" in line:
                current_detail['transaction_type'] = "Debit"
                current_detail['party'] = line.split("Paid to")[1].strip()
            elif "Received from" in line:
                current_detail['transaction_type'] = "Credit"
                current_detail['party'] = line.split("Received from")[1].strip()

            # Extract Amount
            amount_match = amount_pattern.search(line)
            if amount_match:
                amount_str = amount_match.group()
                # Convert the amount to the required format "INR xx.xx"
                formatted_amount = "INR " + amount_str.replace('₹', '').replace(',', '').strip()
                current_detail['amount'] = formatted_amount

            # Extract Transaction ID
            if 'Transaction ID' in line:
                current_detail['transaction_id'] = line.split("Transaction ID")[1].strip()

            # If all details are collected, save and reset the current detail dictionary
            if 'date' in current_detail and 'transaction_type' in current_detail and 'party' in current_detail and 'amount' in current_detail:
                details.append(current_detail)
                current_detail = {}

    return {
        "transactions": details
    }
