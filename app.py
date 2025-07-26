from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from datetime import datetime, timedelta
import os
from functools import wraps
from bson.objectid import ObjectId

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['employee_management']
users_collection = db['users']
attendance_collection = db['attendance']
salary_collection = db['salary']

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('employee_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = users_collection.find_one({'email': email})
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['role'] = user['role']
            session['name'] = user['name']
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('employee_dashboard'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    total_employees = users_collection.count_documents({'role': 'employee'})
    today_attendance = attendance_collection.count_documents({
        'date': datetime.now().strftime('%Y-%m-%d'),
        'check_in': {'$exists': True}
    })
    
    return render_template('admin_dashboard.html', 
                         total_employees=total_employees,
                         today_attendance=today_attendance)

@app.route('/admin/register_employee', methods=['GET', 'POST'])
@admin_required
def register_employee():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        department = request.form['department']
        position = request.form['position']
        salary = float(request.form['salary'])
        
        # Check if email already exists
        if users_collection.find_one({'email': email}):
            flash('Email already exists', 'error')
            return render_template('register_employee.html')
        
        # Create employee
        employee_data = {
            'name': name,
            'email': email,
            'password': generate_password_hash(password),
            'role': 'employee',
            'department': department,
            'position': position,
            'created_at': datetime.now()
        }
        
        employee_id = users_collection.insert_one(employee_data).inserted_id
        
        # Create salary record
        salary_data = {
            'employee_id': employee_id,
            'basic_salary': salary,
            'allowances': 0,
            'deductions': 0,
            'created_at': datetime.now()
        }
        salary_collection.insert_one(salary_data)
        
        flash('Employee registered successfully', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('register_employee.html')

@app.route('/admin/employees')
@admin_required
def view_employees():
    employees = list(users_collection.find({'role': 'employee'}))
    return render_template('view_employees.html', employees=employees)

@app.route('/admin/employee/<employee_id>/profile')
@admin_required
def employee_profile(employee_id):
    employee = users_collection.find_one({'_id': ObjectId(employee_id)})
    attendance_logs = list(attendance_collection.find({'employee_id': ObjectId(employee_id)}).sort('date', -1))
    salary_records = list(salary_collection.find({'employee_id': ObjectId(employee_id)}).sort([('year', -1), ('month', -1)]))
    return render_template('employee_profile.html', employee=employee, attendance_logs=attendance_logs, salary_records=salary_records)


@app.route('/admin/employee/<employee_id>/attendance')
@admin_required
def employee_attendance(employee_id):
    employee = users_collection.find_one({'_id': ObjectId(employee_id)})
    attendance_records = list(attendance_collection.find(
        {'employee_id': ObjectId(employee_id)}
    ).sort('date', -1))
    
    return render_template('employee_attendance.html', 
                         employee=employee, 
                         attendance_records=attendance_records)

@app.route('/admin/manage_salary/<employee_id>', methods=['GET', 'POST'])
@admin_required
def manage_salary(employee_id):
    employee = users_collection.find_one({'_id': ObjectId(employee_id)})
    current_year = datetime.now().year
    current_month = datetime.now().month

    if request.method == 'POST':
        month = int(request.form['month'])
        year = int(request.form['year'])
        fixed_pay = float(request.form.get('fixed_pay', 0))
        variable_pay = float(request.form.get('variable_pay', 0))
        special_allowances = float(request.form.get('special_allowances', 0))
        deductions = float(request.form.get('deductions', 0))
        total = fixed_pay + variable_pay + special_allowances - deductions
        paid_on = datetime.now()
        
        salary_collection.update_one(
            {'employee_id': ObjectId(employee_id), 'month': month, 'year': year},
            {
                '$set': {
                    'fixed_pay': fixed_pay,
                    'variable_pay': variable_pay,
                    'special_allowances': special_allowances,
                    'deductions': deductions,
                    'total': total,
                    'paid_on': paid_on,
                    'month': month,
                    'year': year
                }
            },
            upsert=True
        )
        flash('Salary updated for {}-{}'.format(month, year), 'success')
        return redirect(url_for('manage_salary', employee_id=employee_id))

    # Fetch all salary records for this employee, sorted by year/month desc
    salary_records = list(salary_collection.find({'employee_id': ObjectId(employee_id)}).sort([('year', -1), ('month', -1)]))
    return render_template('manage_salary.html', employee=employee, salary_records=salary_records, current_month=current_month, current_year=current_year)


@app.route('/employee/dashboard')
@login_required
def employee_dashboard():
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    
    employee_id = ObjectId(session['user_id'])
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Check if already checked in today
    today_attendance = attendance_collection.find_one({
        'employee_id': employee_id,
        'date': today
    })
    
    # Get recent attendance
    recent_attendance = list(attendance_collection.find(
        {'employee_id': employee_id}
    ).sort('date', -1).limit(5))
    
    return render_template('employee_dashboard.html', 
                         today_attendance=today_attendance,
                         recent_attendance=recent_attendance)

@app.route('/employee/checkin', methods=['POST'])
@login_required
def checkin():
    employee_id = ObjectId(session['user_id'])
    today = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now()
    
    # Check if already checked in today
    existing_attendance = attendance_collection.find_one({
        'employee_id': employee_id,
        'date': today
    })
    
    if existing_attendance and 'check_in' in existing_attendance:
        flash('Already checked in today', 'error')
    else:
        attendance_data = {
            'employee_id': employee_id,
            'date': today,
            'check_in': current_time,
            'check_in_time': current_time.strftime('%H:%M:%S')
        }
        
        if existing_attendance:
            attendance_collection.update_one(
                {'_id': existing_attendance['_id']},
                {'$set': attendance_data}
            )
        else:
            attendance_collection.insert_one(attendance_data)
        
        flash('Checked in successfully', 'success')
    
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/checkout', methods=['POST'])
@login_required
def checkout():
    employee_id = ObjectId(session['user_id'])
    today = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now()
    
    attendance = attendance_collection.find_one({
        'employee_id': employee_id,
        'date': today,
        'check_in': {'$exists': True}
    })
    
    if not attendance:
        flash('Please check in first', 'error')
    elif 'check_out' in attendance:
        flash('Already checked out today', 'error')
    else:
        check_in_time = attendance['check_in']
        hours_worked = (current_time - check_in_time).total_seconds() / 3600
        
        attendance_collection.update_one(
            {'_id': attendance['_id']},
            {
                '$set': {
                    'check_out': current_time,
                    'check_out_time': current_time.strftime('%H:%M:%S'),
                    'hours_worked': round(hours_worked, 2)
                }
            }
        )
        
        flash('Checked out successfully', 'success')
    
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/attendance')
@login_required
def employee_attendance_logs():
    employee_id = ObjectId(session['user_id'])
    attendance_logs = list(attendance_collection.find(
        {'employee_id': employee_id}
    ).sort('date', -1))
    return render_template('employee_attendance_logs.html', attendance_logs=attendance_logs)

@app.route('/employee/salary')
@login_required
def employee_salary():
    employee_id = ObjectId(session['user_id'])
    salary_records = list(salary_collection.find({'employee_id': employee_id}).sort([('year', -1), ('month', -1)]))
    return render_template('employee_salary.html', salary_records=salary_records)


if __name__ == '__main__':
    # Create admin user if it doesn't exist
    admin = users_collection.find_one({'email': 'admin@company.com'})
    if not admin:
        admin_data = {
            'name': 'System Admin',
            'email': 'admin@company.com',
            'password': generate_password_hash('admin123'),
            'role': 'admin',
            'created_at': datetime.now()
        }
        users_collection.insert_one(admin_data)
        print("Admin user created: admin@company.com / admin123")
    
    app.run(debug=True)