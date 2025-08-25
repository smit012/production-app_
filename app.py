import streamlit as st
import pandas as pd
from datetime import datetime
import io
import gspread
from google.oauth2.service_account import Credentials  # ✅ use google-auth instead

SCOPE = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=SCOPE
)

client = gspread.authorize(creds)

SHEET_NAME = "Production Tracker"
try:
    sheet = client.open(SHEET_NAME).sheet1
except gspread.SpreadsheetNotFound:
    sh = client.create(SHEET_NAME)
    sh.share(creds.service_account_email, perm_type="user", role="writer")
    sheet = sh.sheet1

# ✅ Always ensure header row exists
if not sheet.get_all_values():
    sheet.append_row([
        "Date", "Product Name", "Start Time", "End Time", "Hours",
        "Total Persons", "Actual Production",
        "Per Hour Production", "Per Man Hour", "Packaging Cost", "Remark", "Status"
    ])

# -------------------------------
# Streamlit UI
# -------------------------------
st.set_page_config(page_title="Production Tracker", layout="wide")
st.title("📊 Multi-Task Production Tracker")


if "running_tasks" not in st.session_state:
    st.session_state.running_tasks = {}

# 🔥 Load unfinished tasks from Google Sheets (restore after refresh)
records = sheet.get_all_records()
for idx, row in enumerate(records, start=2):  # start=2 (skip header row)
    if row["Status"] == "Running":
        task_id = f"row_{idx}"
        if task_id not in st.session_state.running_tasks:
            # Rebuild task dict from sheet
            st.session_state.running_tasks[task_id] = {
                "Row": idx,
                "Date": row["Date"],
                "Product Name": row["Product Name"],
                "Start Time": datetime.strptime(row["Start Time"], "%H:%M:%S"),
                "Total Persons": row["Total Persons"],
                "Actual Production": row["Actual Production"],
                "Remark": row.get("Remark", ""),
                "Status": "Running"
            }

# -------------------------------
# Start Task Form
# -------------------------------
with st.form("task_form"):
    product_name = st.text_input("Enter Product Name")
    total_persons = st.number_input("Total Persons", min_value=1, step=1)
    actual_production = st.number_input("Actual Production", min_value=0, step=1)
    remark = st.text_area("Remark (Optional)")
    submitted = st.form_submit_button("▶ Start Task")

    if submitted:
        if product_name and total_persons > 0:
            task_id = str(datetime.now().timestamp())
            start_time = datetime.now()

            # Save running task to Google Sheets immediately
            sheet.append_row([
                start_time.strftime("%d-%m-%Y"),
                product_name,
                start_time.strftime("%H:%M:%S"),
                "", "",  # End Time & Hours empty while running
                total_persons,
                actual_production,
                "", "", "",  # Per hour, per man hour, packaging cost empty
                remark,
                "Running"
            ])

            # Find row index of newly added task
            row_index = len(sheet.get_all_values())

            st.session_state.running_tasks[task_id] = {
                "Row": row_index,
                "Date": start_time.strftime("%d-%m-%Y"),
                "Product Name": product_name,
                "Start Time": start_time,
                "Total Persons": total_persons,
                "Actual Production": actual_production,
                "Remark": remark,
                "Status": "Running"
            }

            st.success(f"Task started: {product_name}")
        else:
            st.error("Please enter Product Name and Persons")

# -------------------------------
# Running Tasks
# -------------------------------
st.subheader("⏳ Running Tasks")
if st.session_state.running_tasks:
    for task_id, task in list(st.session_state.running_tasks.items()):
        col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
        col1.write(f"**{task['Product Name']}** | Persons: {task['Total Persons']} | Started: {task['Start Time'].strftime('%H:%M:%S')}")
        col2.write(f"Total Persons: {task['Total Persons']}") 
        col2.write(f"Actual Production: {task['Actual Production']}")
        col2.write(f"Status: {task['Status']}")

        # End Task
        if col3.button("⏹ End", key=f"end_{task_id}"):
            end_time = datetime.now()
            hours = (end_time - task["Start Time"]).total_seconds() / 3600

            per_hour = task["Actual Production"] / hours if hours > 0 else 0
            per_man_hour = task["Actual Production"] / (hours * task["Total Persons"]) if (hours > 0 and task["Total Persons"] > 0) else 0
            packaging_cost = 50 / per_man_hour if per_man_hour > 0 else 0

            row = task["Row"]

            # 🔥 Update existing row instead of appending
           # sheet.update(f"D{row}", end_time.strftime("%H:%M:%S"))  # End Time
           # sheet.update(f"E{row}", round(hours, 2))                # Hours
           # sheet.update(f"H{row}", round(per_hour, 2))             # Per Hour
            #sheet.update(f"I{row}", round(per_man_hour, 2))         # Per Man Hour
           # sheet.update(f"J{row}", round(packaging_cost, 2))       # Packaging Cost
           # sheet.update(f"L{row}", "Completed")                    # Status

            sheet.update_cell(row, 4, end_time.strftime("%H:%M:%S"))  # Column D = 4
            sheet.update_cell(row, 5, round(hours, 2))                # Column E = 5
            sheet.update_cell(row, 8, round(per_hour, 2))             # Column H = 8
            sheet.update_cell(row, 9, round(per_man_hour, 2))         # Column I = 9
            sheet.update_cell(row, 10, round(packaging_cost, 2))      # Column J = 10
            sheet.update_cell(row, 12, "Completed")                   # Column L = 12


            del st.session_state.running_tasks[task_id]
            st.success(f"✅ Task ended: {task['Product Name']}")

        # Cancel Task
        if col4.button("❌ Cancel", key=f"cancel_{task_id}"):
            row = task["Row"]
            sheet.update_cell(f"L{row}", "Cancelled")
            del st.session_state.running_tasks[task_id]
            st.warning(f"🚫 Task cancelled: {task['Product Name']}")

else:
    st.info("No tasks running...")

# -------------------------------
# Completed Records (from Google Sheets)
# -------------------------------
st.subheader("📑 Completed Records")

expected_headers = [
    "Date", "Product Name", "Start Time", "End Time", "Hours",
    "Total Persons", "Actual Production",
    "Per Hour Production", "Per Man Hour", "Packaging Cost", "Remark", "Status"
]

records = sheet.get_all_records(expected_headers=expected_headers)

if records:
    df = pd.DataFrame(records)
    st.dataframe(df)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Production Data")

    st.download_button(
        label="📥 Download Excel",
        data=buffer,
        file_name="production_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("No completed records yet.")


