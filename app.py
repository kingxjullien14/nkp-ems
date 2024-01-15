import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns

engine = create_engine('sqlite:///nkp_ems_db.db')

# Function to read data from the database for each table
def read_admin_data():
    return pd.read_sql_query("SELECT * FROM admins", engine)

def read_attendance_data():
    return pd.read_sql_query("SELECT * FROM attendances", engine)

def read_employee_data():
    return pd.read_sql_query("SELECT * FROM employees", engine)

def read_leave_data():
    return pd.read_sql_query("SELECT * FROM leaves", engine)

def read_salary_data():
    return pd.read_sql_query("SELECT * FROM salaries", engine)

# Function to check expiration dates and send reminders
def send_reminders():
    today = datetime.now().date()

    employee_data = read_employee_data()

    # Filter employees with passports, visas, and permits expiring soon
    expiring_passports = employee_data[employee_data['passport_expiry_date'].apply(pd.to_datetime).dt.date < today + timedelta(days=30)]
    expiring_visas = employee_data[employee_data['visa_expiry_date'].apply(pd.to_datetime).dt.date < today + timedelta(days=30)]
    expiring_permits = employee_data[employee_data['permit_expiry_date'].apply(pd.to_datetime).dt.date < today + timedelta(days=30)]

    # Display reminders if there are expiring documents
    if not expiring_passports.empty:
        st.warning("Passports Expiring Soon:")
        st.table(expiring_passports[['full_name', 'passport_expiry_date']])

    if not expiring_visas.empty:
        st.warning("Visas Expiring Soon:")
        st.table(expiring_visas[['full_name', 'visa_expiry_date']])

    if not expiring_permits.empty:
        st.warning("Permits Expiring Soon:")
        st.table(expiring_permits[['full_name', 'permit_expiry_date']])

def calculate_salary():
    employee_data = read_employee_data()
    attendance_data = read_attendance_data()

    attendance_data['attendance_date'] = pd.to_datetime(attendance_data['attendance_date']).dt.date

    attendance_data['action_time'] = pd.to_datetime(attendance_data['action_time']).dt.time

    attendance_data['action_datetime'] = attendance_data.apply(
        lambda row: datetime.combine(row['attendance_date'], row['action_time']),
        axis=1
    )
    
    merged_data = pd.merge(attendance_data, employee_data, on='emp_code')

    merged_data['time_difference'] = merged_data.groupby(['emp_code', 'attendance_date'])['action_datetime'].diff()

    merged_data['hours_worked'] = merged_data['time_difference'].dt.total_seconds() / 3600
    
    merged_data['salary'] = merged_data['hours_worked'] * merged_data['hourly_rate']

    merged_data['attendance_date'] = pd.to_datetime(merged_data['attendance_date'])

    merged_data['attendance_month'] = merged_data['attendance_date'].dt.strftime('%Y-%m')

    monthly_salary = merged_data.groupby(['emp_code', 'attendance_month'])['salary'].sum().reset_index()
    
    for index, row in monthly_salary.iterrows():
        emp_code = row['emp_code']
        net_salary = row['salary']
        salary_month = row['attendance_month']
        generate_date = datetime.now()

        insert_query = f"""
        INSERT INTO salaries (emp_code, net_salary, salary_month, generate_date)
        VALUES ('{emp_code}', {net_salary}, '{salary_month}', '{generate_date}')
        """

        with engine.connect() as connection:
            connection.execute(text(insert_query))

    st.table(monthly_salary)
    
    return(monthly_salary)

# Function to generate and display the salary summary report
def generate_salary_summary_report():
    st.subheader("Salary Summary Report")

    # Calculate salary using the existing function
    salary_data = calculate_salary()

    plt.figure(figsize=(10, 6))
    sns.barplot(x='emp_code', y='salary', data=salary_data)
    plt.title('Total Salary Summary')
    plt.xlabel('Employee')
    plt.ylabel('Total Salary')
    st.pyplot(plt)

# Function to generate reports
def generate_reports():
    st.subheader("Generate Reports")

    report_type = st.selectbox("Select Report Type", ["Attendance Summary", "Salary Summary"])

    employee_data = read_employee_data()
    attendance_data = read_attendance_data()
    
    attendance = pd.merge(employee_data, attendance_data, on='emp_code')
    
    if report_type == "Attendance Summary":
        st.subheader("Attendance Summary")
        attendance_summary = attendance.groupby('full_name')['attendance_date'].count().reset_index(name='Total Days Present')
        st.table(attendance_summary)

    elif report_type == "Salary Summary":
        generate_salary_summary_report()


# Function to display the login form
def display_login_form():
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        # Validate admin login credentials
        admin_query = f"SELECT * FROM admins WHERE admin_code = :username AND admin_password = :password"
        admin_result = pd.read_sql_query(admin_query, engine, params={"username": username, "password": password})

        if not admin_result.empty:
            st.success("Logged in as Admin")
            st.session_state.is_admin = True
            st.session_state.current_user = username
            return

        # Validate employee login credentials
        employee_query = "SELECT * FROM employees WHERE emp_code = :username AND emp_password = :password"
        employee_result = pd.read_sql_query(employee_query, engine, params={"username": username, "password": password})

        if not employee_result.empty:
            st.success("Logged in as Employee")
            st.session_state.is_admin = False
            st.session_state.current_user = username
            return

        st.error("Invalid username or password")

# Staff Leave Application
def staff_leave_application():
    st.subheader("Leave Application")

    emp_code = st.session_state.current_user
    leave_subject = st.text_input("Leave Subject")
    leave_date = st.date_input("Select Leave Date", [])
    leave_message = st.text_area("Leave Message")
    leave_type = st.selectbox("Leave Type", ["Paid", "Unpaid"])

    if st.button("Submit Leave Request"):
        leave_request = pd.DataFrame({
            'emp_code': [emp_code],
            'leave_subject': [leave_subject],
            'leave_date': [leave_date],
            'leave_message': [leave_message],
            'leave_type': [leave_type],
            'leave_status': ['pending'],
            'apply_date': [datetime.now()],
            'admin_approval_date': [None]
        })

        leave_request.to_sql('leaves', con=engine, index=False, if_exists='append')
        st.success("Leave request submitted successfully!")

def admin_leave_approval():
    st.subheader("Leave Approval (Admin View)")
    
    leave_data = read_leave_data()

    pending_leave_requests = pd.read_sql_query("SELECT * FROM leaves WHERE leave_status = 'pending'", engine)

    if not pending_leave_requests.empty:
        st.table(pending_leave_requests[['leave_id','emp_code', 'leave_subject', 'leave_dates', 'leave_message', 'leave_type', 'apply_date']])

        leave_to_approve = st.selectbox("Select Leave Request to Approve/Deny", pending_leave_requests['leave_id'].tolist())

        approval_status = st.radio("Choose Approval Status", ['Approve', 'Deny'])

        if st.button("Submit Approval"):
            approval_date = datetime.now()
            leave_data.loc[leave_data['leave_id'] == leave_to_approve, 'leave_status'] = 'approve' if approval_status == 'Approve' else 'reject'
            leave_data.loc[leave_data['leave_id'] == leave_to_approve, 'admin_approval_date'] = approval_date

            leave_data.to_sql('leaves', con=engine, index=False, if_exists='replace')

            st.success(f"Leave request {approval_status}d successfully on {approval_date}")
    else:
        st.info("No pending leave requests.")

# Staff Attendance Punch In/Out
def staff_attendance():
    st.subheader("Attendance (Punch In/Out)")

    emp_code = st.session_state.current_user
    action_name = st.radio("Select Action", ['punchin', 'punchout'])
    emp_desc = st.text_input("Description")

    if st.button("Submit Attendance"):
        attendance_entry = pd.DataFrame({
            'emp_code': [emp_code],
            'attendance_date': [datetime.now().date()],
            'action_name': [action_name],
            'action_time': [datetime.now().strftime("%H:%M:%S")],
            'emp_desc': [emp_desc]
        })

        attendance_entry.to_sql('attendances', con=engine, index=False, if_exists='append')
        st.success(f"Attendance {action_name} successfully!")

# Function to update or add employee information
def add_employee_info():
    # Get the current year
    current_year = datetime.now().year

    # Set the desired date range (e.g., from 1900 to the current year)
    min_date = datetime(1900, 1, 1)
    max_dob_date = datetime(current_year,12, 31)
    max_date = datetime(2099, 12, 31)
    
    # Add Employee Section
    st.subheader("Add Employee")
    new_emp_code = st.text_input("Employee Code")
    new_emp_password = st.text_input("Password", type="password")
    new_full_name = st.text_input("Full Name")
    new_dob = st.date_input("Date of Birth", min_value=min_date, max_value=max_dob_date)
    new_gender = st.radio("Gender", ["male", "female"])
    new_nationality = st.text_input("Nationality")
    new_address = st.text_input("Address")
    new_phone_number = st.text_input("Phone Number")
    new_email = st.text_input("Email")
    new_passport_number = st.text_input("Passport Number")
    new_passport_country = st.text_input("Passport Country")
    new_passport_issue_date = st.date_input("Passport Issue Date", min_value=min_date, max_value=max_date)
    new_passport_expiry_date = st.date_input("Passport Expiry Date", min_value=min_date, max_value=max_date)
    new_visa_type = st.selectbox("Visa Type", ["Single Entry Visa", "Multiple Entry Visa", "Transit Visa"])
    new_visa_number = st.text_input("Visa Number")
    new_visa_issue_date = st.date_input("Visa Issue Date", min_value=min_date, max_value=max_date)
    new_visa_expiry_date = st.date_input("Visa Expiry Date", min_value=min_date, max_value=max_date)
    new_visa_status = st.selectbox("Visa Status", ["Approved", "Denied", "Pending"])
    new_permit_type = st.selectbox("Permit Type", ["Employment Pass", "Professional Visit Pass", "Residence Pass-Talent"])
    new_permit_number = st.text_input("Permit Number")
    new_permit_issue_date = st.date_input("Permit Issue Date", min_value=min_date, max_value=max_date)
    new_permit_expiry_date = st.date_input("Permit Expiry Date", min_value=min_date, max_value=max_date)
    new_hourly_rate = st.number_input("Hourly Rate", min_value=0)

    if st.button("Add Employee"):
        add_request = pd.DataFrame({
            'emp_code': [new_emp_code],
            'emp_password': [new_emp_password],
            'full_name': [new_full_name],
            'dob': [new_dob],
            'gender': [new_gender],
            'nationality': [new_nationality],
            'address': [new_address],
            'phone_number': [new_phone_number],
            'email': [new_email],
            'passport_number': [new_passport_number],
            'passport_country': [new_passport_country],
            'passport_issue_date': [new_passport_issue_date],
            'passport_expiry_date': [new_passport_expiry_date],
            'visa_type': [new_visa_type],
            'visa_number': [new_visa_number],
            'visa_issue_date': [new_visa_issue_date],
            'visa_expiry_date': [new_visa_expiry_date],
            'visa_status': [new_visa_status],
            'permit_type': [new_permit_type],
            'permit_number': [new_permit_number],
            'permit_issue_date': [new_permit_issue_date],
            'permit_expiry_date': [new_permit_expiry_date],
            'hourly_rate': [new_hourly_rate]
        })
        
        add_request.to_sql('employees', con=engine, index=False, if_exists='append')
        st.success("Employee added successfully!")

def update_employee_info(employees):
    # Get the current year
    current_year = datetime.now().year

    # Set the desired date range (e.g., from 1900 to the current year)
    min_date = datetime(1900, 1, 1)
    max_dob_date = datetime(current_year,12, 31)
    max_date = datetime(2099, 12, 31)
    
    # Update Employee Section
    st.subheader("Update Employee")
    selected_employee_to_update = st.selectbox("Select Employee to Update", employees['emp_code'].unique())

    # Retrieve existing details of the selected employee
    selected_employee_details = employees[employees['emp_code'] == selected_employee_to_update].iloc[0]

    # Input fields for updating employee details
    updated_emp_code = st.text_input("Employee Code", value=selected_employee_details['emp_code'])
    updated_emp_password = st.text_input("Password", type="password", value=selected_employee_details['emp_password'])
    updated_full_name = st.text_input("Full Name", value=selected_employee_details['full_name'])
    updated_dob = st.text_input("Date of Birth", value=selected_employee_details['dob'])
    updated_gender = st.selectbox("Gender", ['male', 'female'], index=0 if selected_employee_details['gender'] == 'male' else 1)
    updated_nationality = st.text_input("Nationality", value=selected_employee_details['nationality'])
    updated_address = st.text_area("Address", value=selected_employee_details['address'])
    updated_phone_number = st.text_input("Phone Number", value=selected_employee_details['phone_number'])
    updated_email = st.text_input("Email", value=selected_employee_details['email'])
    updated_passport_number = st.text_input("Passport Number", value=selected_employee_details['passport_number'])
    updated_passport_country = st.text_input("Passport Country", value=selected_employee_details['passport_country'])
    updated_passport_issue_date = st.text_input("Passport Issue Date", value=selected_employee_details['passport_issue_date'])
    updated_passport_expiry_date = st.text_input("Passport Expiry Date", value=selected_employee_details['passport_expiry_date'])
    updated_visa_type = st.selectbox("Visa Type", ['Single Entry Visa', 'Multiple Entry Visa', 'Transit Visa'],
                                 index=0 if selected_employee_details['visa_type'] == 'Single Entry Visa' else 1 if selected_employee_details['visa_type'] == 'Multiple Entry Visa' else 2,
                                 key="visa_type")
    updated_visa_number = st.text_input("Visa Number", value=selected_employee_details['visa_number'], key="visa_number")
    updated_visa_issue_date = st.text_input("Visa Issue Date", value=selected_employee_details['visa_issue_date'], key="visa_issue_date")
    updated_visa_expiry_date = st.text_input("Visa Expiry Date", value=selected_employee_details['visa_expiry_date'], key="visa_expiry_date")
    updated_visa_status = st.selectbox("Visa Status", ['Approved', 'Denied', 'Pending'],
                                    index=0 if selected_employee_details['visa_status'] == 'Approved' else 1 if selected_employee_details['visa_status'] == 'Denied' else 2,
                                    key="visa_status")
    updated_permit_type = st.selectbox("Permit Type", ['Employment Pass', 'Professional Visit Pass', 'Residence Pass-Talent'],
                                   index=0 if selected_employee_details['permit_type'] == 'Employment Pass' else 1 if selected_employee_details['permit_type'] == 'Professional Visit Pass' else 2,
                                   key="permit_type")
    updated_permit_number = st.text_input("Permit Number", value=selected_employee_details['permit_number'])
    updated_permit_issue_date = st.text_input("Permit Issue Date", value=selected_employee_details['permit_issue_date'])
    updated_permit_expiry_date = st.text_input("Permit Expiry Date", value=selected_employee_details['permit_expiry_date'])
    updated_hourly_rate = st.number_input("Hourly Rate", value=selected_employee_details['hourly_rate'])

    if st.button("Update Employee"):
        # Create an update query
        update_query = text(f"""
            UPDATE employees
            SET
            emp_code = :emp_code,
            emp_password = :emp_password,
            full_name = :full_name,
            dob = :dob,
            gender = :gender,
            nationality = :nationality,
            address = :address,
            phone_number = :phone_number,
            email = :email,
            passport_number = :passport_number,
            passport_country = :passport_country,
            passport_issue_date = :passport_issue_date,
            passport_expiry_date = :passport_expiry_date,
            visa_type = :visa_type,
            visa_number = :visa_number,
            visa_issue_date = :visa_issue_date,
            visa_expiry_date = :visa_expiry_date,
            visa_status = :visa_status,
            permit_type = :permit_type,
            permit_number = :permit_number,
            permit_issue_date = :permit_issue_date,
            permit_expiry_date = :permit_expiry_date,
            hourly_rate = :hourly_rate
            WHERE emp_code = :emp_code
        """)

        # Execute the update query        
        with engine.connect() as connection:
            trans = connection.begin()
            try:
                connection.execute(update_query, {
                    "emp_code": updated_emp_code,
                    "emp_password": updated_emp_password,
                    "full_name": updated_full_name,
                    "dob": updated_dob,
                    "gender": updated_gender,
                    "nationality": updated_nationality,
                    "address": updated_address,
                    "phone_number": updated_phone_number,
                    "email": updated_email,
                    "passport_number": updated_passport_number,
                    "passport_country": updated_passport_country,
                    "passport_issue_date": updated_passport_issue_date,
                    "passport_expiry_date": updated_passport_expiry_date,
                    "visa_type": updated_visa_type,
                    "visa_number": updated_visa_number,
                    "visa_issue_date": updated_visa_issue_date,
                    "visa_expiry_date": updated_visa_expiry_date,
                    "visa_status": updated_visa_status,
                    "permit_type": updated_permit_type,
                    "permit_number": updated_permit_number,
                    "permit_issue_date": updated_permit_issue_date,
                    "permit_expiry_date": updated_permit_expiry_date,
                    "hourly_rate": updated_hourly_rate
                })
                trans.commit()
                st.success("Employee information updated successfully!")
            except Exception as e:
                trans.rollback()
                st.error(f"Error updating employee information: {str(e)}")

def delete_employee_info(employees):
    # Delete Employee Section
    st.subheader("Delete Employee")
    selected_employee_to_delete = st.selectbox("Select Employee to Delete", employees['emp_code'].unique())

    if st.button("Delete Employee"):
        # Perform SQL delete operation to remove the selected employee
        delete_query = f"""
            DELETE FROM employees WHERE emp_code = '{selected_employee_to_delete}';
        """
        with engine.connect() as connection:
            connection.execute(delete_query)
        st.success("Employee deleted successfully!")

# Function to read leave data for a specific staff member
def read_staff_leave_data(emp_code):
    query = f"SELECT * FROM leaves WHERE emp_code = '{emp_code}'"
    return pd.read_sql_query(query, engine)

# Function to display staff leave table
def display_staff_leave_table(emp_code):
    st.subheader("Requested Leaves")
    leave_data = read_staff_leave_data(emp_code)

    if not leave_data.empty:
        st.table(leave_data)
    else:
        st.info("No leave requests found.")

# Function to check if the user is logged in
def is_logged_in():
    return 'is_logged_in' in st.session_state

# Function to display the logout button
def display_logout_button():
    st.subheader("Logout")
    if st.button("Logout"):
        st.session_state.clear()
        st.success("Logged out successfully!")

# Main function for the Streamlit app
def main():
    # Display the logo
    logo_path = "full.png"
    st.image(logo_path, use_column_width=True)
    
    st.markdown(
        """
        <div style="text-align:center">
            <h1 style="font-size:1.5em;">Employee Management System</h1>
        </div>
        <br>
        """,
        unsafe_allow_html=True
    )
    
    attendance_data = read_attendance_data()
    salary_data = read_salary_data()

    # Initialize session state
    if 'is_admin' not in st.session_state:
        st.session_state.is_admin = False
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None

    # Check if the user is logged in
    if not st.session_state.is_admin and st.session_state.current_user is None:
        display_login_form()
        return
    
    st.subheader(f"Welcome, {st.session_state.current_user}!")
    # Sidebar for navigation
    if st.session_state.is_admin:
        page = st.sidebar.selectbox("Select a Page", ["Employee Records", "Add Employee", "Update Employee", "Attendance", "Leave Requests", "Payroll", "Reports"])
    else:
        page = st.sidebar.selectbox("Select a Page", ["Employee Details", "Salary", "Punch In/Out", "Leave Requests"])
        
    # Logout button
    if st.session_state.current_user is not None:
        if st.sidebar.button("Logout"):
            st.session_state.is_admin = False
            st.session_state.current_user = None
            st.success("Logged out successfully!")

    if st.session_state.is_admin:
        # Admin has access to all pages
        if page == "Employee Records":
            st.subheader("Employee Records (Admin View)")
            employees = pd.read_sql_query("SELECT * FROM employees", engine)
            st.table(employees)
            delete_employee_info(employees)
        elif page == "Add Employee":
            add_employee_info()
        elif page == "Update Employee":
            employees = pd.read_sql_query("SELECT * FROM employees", engine)
            update_employee_info(employees)
        elif page == "Attendance":
            st.subheader("Attendance Tracking (Admin View)")
            st.table(attendance_data)
        elif page == "Leave Requests":
            admin_leave_approval()
        elif page == "Payroll":
            st.subheader("Payroll (Admin View)")
            payroll_result = salary_data
            st.table(payroll_result)
        elif page == "Reports":
            send_reminders()
            generate_reports()
    else:
        # Staff has limited access
        if page == "Employee Details":
            st.subheader(f"Employee Details ({st.session_state.current_user} View)")
            staff_data = pd.read_sql_query(f"SELECT * FROM employees WHERE emp_code = '{st.session_state.current_user}'", engine)
            st.table(staff_data)
        elif page == "Salary":
            st.subheader(f"Salary ({st.session_state.current_user} View)")
            staff_payroll = salary_data[salary_data['emp_code'] == st.session_state.current_user]
            st.table(staff_payroll)
        elif page == "Punch In/Out":
            staff_attendance()
        elif page == "Leave Requests":
            display_staff_leave_table(st.session_state.current_user)
            staff_leave_application()
        elif page == "Reports":
            st.warning("You do not have access to reports.")

    

# Run the app
if __name__ == "__main__":
    main()
