import os
import json
import base64
import sqlite3
import shutil
from datetime import datetime, timedelta
from functools import wraps
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
import io
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)

# Database Configuration - PostgreSQL for production, SQLite for development
DATABASE_URI = os.environ.get('DATABASE_URL')
if DATABASE_URI:
    # Railway PostgreSQL URLs start with 'postgres://' but SQLAlchemy needs 'postgresql://'
    if DATABASE_URI.startswith("postgres://"):
        DATABASE_URI = DATABASE_URI.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
    print("Using PostgreSQL database (Production)")
else:
    # Development: SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///municipal_police_v3.db'
    print("Using SQLite database (Development)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # 8-hour sessions

db = SQLAlchemy(app)

# ======================== DATABASE MODELS ========================

# ============= TEMPORARY MIGRATION FUNCTION =============
def run_migration_if_needed():
    """Τρέχει το migration αν χρειάζεται - ΜΟΝΟ ΜΙΑ ΦΟΡΑ"""
    try:
        from sqlalchemy import text
        
        print("🔄 Checking if migration is needed...")
        
        # Έλεγχος αν υπάρχει η στήλη 'article'
        result = db.session.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'violations_data' AND column_name = 'article'"
        ))
        
        if result.fetchone():
            print("✅ Migration already completed!")
            return
        
        print("🚀 Running PostgreSQL migration...")
        
        commands = [
            'ALTER TABLE violations_data ADD COLUMN article TEXT',
            'ALTER TABLE violations_data ADD COLUMN article_paragraph TEXT',
            'ALTER TABLE violations_data ADD COLUMN remove_circulation_elements BOOLEAN DEFAULT FALSE',
            'ALTER TABLE violations_data ADD COLUMN circulation_removal_days INTEGER DEFAULT 0',
            'ALTER TABLE violations_data ADD COLUMN remove_circulation_license BOOLEAN DEFAULT FALSE',
            'ALTER TABLE violations_data ADD COLUMN circulation_license_removal_days INTEGER DEFAULT 0',
            'ALTER TABLE violations_data ADD COLUMN remove_driving_license BOOLEAN DEFAULT FALSE',
            'ALTER TABLE violations_data ADD COLUMN driving_license_removal_days INTEGER DEFAULT 0',
            'ALTER TABLE violations_data ADD COLUMN half_fine_motorcycles BOOLEAN DEFAULT FALSE',
            'ALTER TABLE violations_data ADD COLUMN parking_special_provision BOOLEAN DEFAULT FALSE',
            'ALTER TABLE violations_data ADD COLUMN is_active BOOLEAN DEFAULT TRUE'
        ]
        
        success_count = 0
        for cmd in commands:
            try:
                db.session.execute(text(cmd))
                print(f"✅ Added column: {cmd.split()[4]}")
                success_count += 1
            except Exception as e:
                print(f"⚠️ Column already exists: {cmd.split()[4]}")
        
        db.session.commit()
        print(f"🎉 Migration completed! Added {success_count} new columns")
        
    except Exception as e:
        print(f"❌ Migration error: {e}")
        db.session.rollback()

class User(db.Model):
    """Πίνακας Χρηστών (Δημοτικοί Αστυνομικοί + Admin + PowerUser)"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    rank = db.Column(db.String(50), nullable=False)  # Βαθμός
    role = db.Column(db.String(20), nullable=False, default='officer')  # 'admin', 'poweruser', 'officer'
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Σχέσεις
    violations = db.relationship('Violation', backref='officer', lazy=True)
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('MessageRecipient', backref='recipient_user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def full_name(self):
        return f"{self.rank} {self.first_name} {self.last_name}"
    
    @property
    def role_display(self):
        """Εμφάνιση ρόλου στα ελληνικά"""
        role_map = {
            'admin': 'Διαχειριστής',
            'poweruser': 'Επόπτης',
            'officer': 'Αστυνομικός'
        }
        return role_map.get(self.role, self.role)
    
    def can_manage_users(self):
        """Έλεγχος αν μπορεί να διαχειρίζεται χρήστες"""
        return self.role == 'admin'
    
    def can_edit_violations(self):
        """Έλεγχος αν μπορεί να επεξεργάζεται παραβάσεις"""
        return self.role == 'admin'
    
    def can_view_admin_dashboard(self):
        """Έλεγχος αν μπορεί να βλέπει admin dashboard"""
        return self.role in ['admin', 'poweruser']
    
    def can_send_mass_messages(self):
        """Έλεγχος αν μπορεί να στέλνει μαζικά μηνύματα"""
        return self.role in ['admin', 'poweruser']

class Message(db.Model):
    """Πίνακας Μηνυμάτων"""
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_mass_message = db.Column(db.Boolean, default=False)  # Για μαζικά μηνύματα
    
    # Σχέσεις
    recipients = db.relationship('MessageRecipient', backref='message', lazy=True, cascade='all, delete-orphan')

class MessageRecipient(db.Model):
    """Πίνακας Παραληπτών Μηνυμάτων"""
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)

class DynamicField(db.Model):
    """Πίνακας Δυναμικών Πεδίων (χρώματα, τύποι οχημάτων)"""
    id = db.Column(db.Integer, primary_key=True)
    field_type = db.Column(db.String(50), nullable=False)  # 'vehicle_color' or 'vehicle_type'
    value = db.Column(db.String(100), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

class ViolationsData(db.Model):
    """Πίνακας Τύπων Παραβάσεων"""
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    paragraph = db.Column(db.String(100), nullable=True)
    
    # Άρθρο ΚΟΚ
    article = db.Column(db.String(20), nullable=True)  # π.χ. "7", "38", "49"
    article_paragraph = db.Column(db.String(20), nullable=True)  # π.χ. "2β", "3η", "4", "2ιβ"
    
    # Πρόστιμα
    fine_cars = db.Column(db.Numeric(8,2), nullable=False)
    fine_motorcycles = db.Column(db.Numeric(8,2), nullable=True)
    fine_trucks = db.Column(db.Numeric(8,2), nullable=True)
    half_fine_motorcycles = db.Column(db.Boolean, default=False)  # Μισό πρόστιμο σε δίκυκλα
    
    # Αφαιρέσεις - Στοιχεία Κυκλοφορίας
    remove_circulation_elements = db.Column(db.Boolean, default=False)
    circulation_removal_days = db.Column(db.Integer, nullable=True)  # 10 ή 40 ημέρες
    
    # Αφαιρέσεις - Άδεια Κυκλοφορίας
    remove_circulation_license = db.Column(db.Boolean, default=False)
    circulation_license_removal_days = db.Column(db.Integer, nullable=True)
    
    # Αφαιρέσεις - Άδεια Οδήγησης
    remove_driving_license = db.Column(db.Boolean, default=False)
    driving_license_removal_days = db.Column(db.Integer, nullable=True)
    
    # Ειδική διάταξη για στάθμευση
    parking_special_provision = db.Column(db.Boolean, default=False)  # Άρθρο 7: Αφαίρεση στοιχείων αντί άδειας οδήγησης
    
    # Μεταδεδομένα
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def full_article(self):
        """Επιστρέφει το πλήρες άρθρο (άρθρο + παράγραφος)"""
        if self.article and self.article_paragraph:
            return f"Άρθρο {self.article} παρ. {self.article_paragraph}"
        elif self.article:
            return f"Άρθρο {self.article}"
        return ""
    
    @property
    def display_name(self):
        """Επιστρέφει το όνομα για εμφάνιση στη φόρμα"""
        article_part = f" ({self.full_article})" if self.full_article else ""
        return f"{self.description}{article_part}"
    
    def get_fine_for_vehicle_type(self, vehicle_type):
        """Επιστρέφει το πρόστιμο ανάλογα με τον τύπο οχήματος"""
        if vehicle_type.lower() in ['μοτοσικλέτα', 'μοτοποδήλατο', 'δίκυκλο']:
            if self.half_fine_motorcycles and self.fine_motorcycles:
                return self.fine_motorcycles / 2
            return self.fine_motorcycles or self.fine_cars
        elif vehicle_type.lower() in ['φορτηγό', 'λεωφορείο']:
            return self.fine_trucks or self.fine_cars
        return self.fine_cars

class Violation(db.Model):
    """Πίνακας Παραβάσεων"""
    id = db.Column(db.Integer, primary_key=True)
    
    # Στοιχεία Οχήματος
    license_plate = db.Column(db.String(20), nullable=False)
    vehicle_brand = db.Column(db.String(50), nullable=False)
    vehicle_color = db.Column(db.String(50), nullable=False)
    vehicle_type = db.Column(db.String(20), nullable=False)
    
    # Στοιχεία Παράβασης
    violation_date = db.Column(db.Date, nullable=False)
    violation_time = db.Column(db.Time, nullable=False)
    street = db.Column(db.String(100), nullable=False)
    street_number = db.Column(db.String(10), nullable=False)
    selected_violations = db.Column(db.Text, nullable=False)  # JSON string
    
    # Επιτόπια Μέτρα
    plates_removed = db.Column(db.Boolean, default=False)
    license_removed = db.Column(db.Boolean, default=False)
    registration_removed = db.Column(db.Boolean, default=False)
    
    # Φωτογραφία
    photo_filename = db.Column(db.String(255), nullable=True)
    
    # Στοιχεία Οδηγού (optional - μόνο αν είναι παρών)
    driver_last_name = db.Column(db.String(50), nullable=True)
    driver_first_name = db.Column(db.String(50), nullable=True)
    driver_father_name = db.Column(db.String(50), nullable=True)
    driver_afm = db.Column(db.String(20), nullable=True)
    driver_signature = db.Column(db.Text, nullable=True)  # Base64 encoded signature
    
    # Προστίμα και Άρθρα
    violation_articles = db.Column(db.Text, nullable=True)  # JSON string με άρθρα
    total_fine_amount = db.Column(db.Numeric(8,2), nullable=True)  # Συνολικό ποσό προστίμου
    fine_breakdown = db.Column(db.Text, nullable=True)  # JSON string με ανάλυση προστίμων
    
    # Μεταδεδομένα
    officer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_selected_violations_list(self):
        """Επιστρέφει τις επιλεγμένες παραβάσεις ως λίστα"""
        try:
            return json.loads(self.selected_violations)
        except:
            return []
    
    def get_violation_articles_list(self):
        """Επιστρέφει τα άρθρα παραβάσεων ως λίστα"""
        try:
            return json.loads(self.violation_articles) if self.violation_articles else []
        except:
            return []
    
    def get_fine_breakdown_list(self):
        """Επιστρέφει την ανάλυση προστίμων ως λίστα"""
        try:
            return json.loads(self.fine_breakdown) if self.fine_breakdown else []
        except:
            return []
    
    def get_fine_breakdown_dict(self):
        """Επιστρέφει την ανάλυση προστίμων ως dictionary"""
        try:
            if self.fine_breakdown:
                data = json.loads(self.fine_breakdown)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return [data]
            return []
        except:
            return []
    
    @property
    def formatted_fine_amount(self):
        """Επιστρέφει το ποσό προστίμου μορφοποιημένο"""
        if self.total_fine_amount:
            return f"{float(self.total_fine_amount):.2f}€"
        return "0.00€"

class Notification(db.Model):
    """Πίνακας Ειδοποιήσεων"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default='info')  # 'info', 'warning', 'error', 'success'
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Σχέσεις
    user = db.relationship('User', backref='notifications', lazy=True)
    
    @property
    def icon(self):
        """Επιστρέφει το κατάλληλο icon για τον τύπο ειδοποίησης"""
        icons = {
            'info': 'fas fa-info-circle',
            'warning': 'fas fa-exclamation-triangle',
            'error': 'fas fa-times-circle',
            'success': 'fas fa-check-circle',
            'message': 'fas fa-envelope'
        }
        return icons.get(self.type, 'fas fa-bell')
    
    @property
    def css_class(self):
        """Επιστρέφει την κατάλληλη CSS κλάση για τον τύπο ειδοποίησης"""
        classes = {
            'info': 'alert-info',
            'warning': 'alert-warning', 
            'error': 'alert-danger',
            'success': 'alert-success',
            'message': 'alert-primary'
        }
        return classes.get(self.type, 'alert-info')

# ======================== MIGRATION FUNCTIONALITY ========================

def database_migration():
    """
    Μετάβαση δεδομένων από municipal_police_v2.db σε municipal_police_v3.db
    Επιστρέφει dictionary με αποτελέσματα
    """
    results = {
        'success': False,
        'message': '',
        'stats': {},
        'errors': []
    }
    
    old_db_path = 'municipal_police_v2.db'
    new_db_path = 'municipal_police_v3.db'
    
    # Έλεγχος αν υπάρχει η παλιά βάση
    if not os.path.exists(old_db_path):
        results['message'] = f'Δεν βρέθηκε η παλιά βάση δεδομένων ({old_db_path})'
        return results
    
    # Δημιουργία αντιγράφου ασφαλείας
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f'municipal_police_v2_backup_{timestamp}.db'
        shutil.copy2(old_db_path, backup_name)
        results['backup_file'] = backup_name
    except Exception as e:
        results['errors'].append(f'Σφάλμα δημιουργίας αντιγράφου: {str(e)}')
        return results
    
    try:
        # Σύνδεση με την παλιά βάση
        old_conn = sqlite3.connect(old_db_path)
        old_conn.row_factory = sqlite3.Row
        old_cursor = old_conn.cursor()
        
        # Δημιουργία των νέων πινάκων
        with app.app_context():
            db.create_all()
        
        # Σύνδεση με τη νέα βάση
        new_conn = sqlite3.connect(new_db_path)
        new_cursor = new_conn.cursor()
        
        # Μετάβαση δεδομένων
        migration_stats = {}
        
        # Μετάβαση χρηστών
        old_cursor.execute('SELECT * FROM user')
        users = old_cursor.fetchall()
        
        user_count = 0
        for user in users:
            # Καθορισμός ρόλου βάσει του παλιού συστήματος
            role = 'admin' if user.get('role') == 'admin' else 'officer'
            
            new_cursor.execute('''
                INSERT OR REPLACE INTO user (
                    id, username, email, password_hash, first_name, last_name,
                    rank, role, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user['id'], user['username'], user['email'], user['password_hash'],
                user['first_name'], user['last_name'], user['rank'], role,
                user['is_active'], user['created_at']
            ))
            user_count += 1
        
        migration_stats['users'] = user_count
        
        # Μετάβαση δυναμικών πεδίων
        old_cursor.execute('SELECT * FROM dynamic_field')
        fields = old_cursor.fetchall()
        
        field_count = 0
        for field in fields:
            new_cursor.execute('''
                INSERT OR REPLACE INTO dynamic_field (
                    id, field_type, value, created_by, created_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                field['id'], field['field_type'], field['value'],
                field['created_by'], field['created_at'], field['is_active']
            ))
            field_count += 1
        
        migration_stats['dynamic_fields'] = field_count
        
        # Μετάβαση παραβάσεων
        old_cursor.execute('SELECT * FROM violation')
        violations = old_cursor.fetchall()
        
        violation_count = 0
        for violation in violations:
            # Προσθήκη default τιμών για τα νέα πεδία αν δεν υπάρχουν
            violation_articles = violation.get('violation_articles', None)
            total_fine_amount = violation.get('total_fine_amount', None) 
            fine_breakdown = violation.get('fine_breakdown', None)
            
            new_cursor.execute('''
                INSERT OR REPLACE INTO violation (
                    id, license_plate, vehicle_brand, vehicle_color, vehicle_type,
                    violation_date, violation_time, street, street_number,
                    selected_violations, plates_removed, license_removed,
                    registration_removed, photo_filename, driver_last_name,
                    driver_first_name, driver_father_name, driver_afm,
                    driver_signature, violation_articles, total_fine_amount,
                    fine_breakdown, officer_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                violation['id'], violation['license_plate'], violation['vehicle_brand'],
                violation['vehicle_color'], violation['vehicle_type'], violation['violation_date'],
                violation['violation_time'], violation['street'], violation['street_number'],
                violation['selected_violations'], violation['plates_removed'],
                violation['license_removed'], violation['registration_removed'],
                violation['photo_filename'], violation['driver_last_name'],
                violation['driver_first_name'], violation['driver_father_name'],
                violation['driver_afm'], violation['driver_signature'],
                violation_articles, total_fine_amount, fine_breakdown,
                violation['officer_id'], violation['created_at'], violation['updated_at']
            ))
            violation_count += 1
        
        migration_stats['violations'] = violation_count
        
        # Commit αλλαγών
        new_conn.commit()
        
        # Στατιστικά για τη νέα βάση
        new_cursor.execute('SELECT COUNT(*) FROM user WHERE role = "admin"')
        admin_count = new_cursor.fetchone()[0]
        
        new_cursor.execute('SELECT COUNT(*) FROM user WHERE role = "officer"')
        officer_count = new_cursor.fetchone()[0]
        
        new_cursor.execute('SELECT COUNT(*) FROM violation WHERE total_fine_amount IS NOT NULL')
        violations_with_fines = new_cursor.fetchone()[0]
        
        migration_stats.update({
            'admin_users': admin_count,
            'officer_users': officer_count,
            'violations_with_fines': violations_with_fines
        })
        
        results.update({
            'success': True,
            'message': 'Η μετάβαση ολοκληρώθηκε επιτυχώς!',
            'stats': migration_stats
        })
        
    except Exception as e:
        results['message'] = f'Σφάλμα κατά τη μετάβαση: {str(e)}'
        results['errors'].append(str(e))
    
    finally:
        try:
            old_conn.close()
            new_conn.close()
        except:
            pass
    
    return results

# ======================== AUTHENTICATION DECORATORS ========================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Παρακαλώ συνδεθείτε για να συνεχίσετε.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Παρακαλώ συνδεθείτε για να συνεχίσετε.', 'warning')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or not user.can_view_admin_dashboard():
            flash('Δεν έχετε δικαίωμα πρόσβασης σε αυτή τη σελίδα.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def poweruser_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Παρακαλώ συνδεθείτε για να συνεχίσετε.', 'warning')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or user.role not in ['admin', 'poweruser']:
            flash('Δεν έχετε δικαίωμα πρόσβασης σε αυτή τη σελίδα.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ======================== MIGRATION ROUTES ========================

@app.route('/admin/migrate')
@admin_required
def migration_page():
    """Σελίδα μετάβασης δεδομένων"""
    # Έλεγχος αν υπάρχει η παλιά βάση
    old_db_exists = os.path.exists('municipal_police_v2.db')
    new_db_exists = os.path.exists('municipal_police_v3.db')
    
    return render_template('admin/migration.html', 
                         old_db_exists=old_db_exists,
                         new_db_exists=new_db_exists)

@app.route('/admin/run-migration', methods=['POST'])
@admin_required
def run_migration():
    """Εκτέλεση μετάβασης δεδομένων"""
    results = database_migration()
    
    if results['success']:
        flash('Η μετάβαση ολοκληρώθηκε επιτυχώς!', 'success')
    else:
        flash(f'Σφάλμα μετάβασης: {results["message"]}', 'danger')
    
    return render_template('admin/migration_result.html', results=results)

# ======================== MAIN ROUTES ========================

@app.route('/')
def index():
    """Αρχική σελίδα - ανακατεύθυνση σε login ή dashboard"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Σελίδα σύνδεσης"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password) and user.is_active:
            session['user_id'] = user.id
            session['username'] = user.username
            session['user_role'] = user.role
            session.permanent = True
            
            flash(f'Καλώς ήρθατε, {user.full_name}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Λάθος στοιχεία σύνδεσης ή ανενεργός λογαριασμός.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Αποσύνδεση χρήστη"""
    session.clear()
    flash('Αποσυνδεθήκατε επιτυχώς.', 'info')
    return redirect(url_for('login'))

# ======================== NOTIFICATION ROUTES ========================

@app.route('/api/notifications')
@login_required
def get_notifications():
    """API endpoint για λήψη ειδοποιήσεων"""
    user_id = session['user_id']
    
    # Λήψη μη αναγνωσμένων ειδοποιήσεων
    notifications = Notification.query.filter_by(user_id=user_id)\
        .order_by(Notification.created_at.desc())\
        .limit(10).all()
    
    unread_count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    
    notifications_data = []
    for notification in notifications:
        notifications_data.append({
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'type': notification.type,
            'is_read': notification.is_read,
            'created_at': notification.created_at.isoformat(),
            'icon': notification.icon
        })
    
    return jsonify({
        'notifications': notifications_data,
        'unread_count': unread_count
    })

@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Σήμανση ειδοποίησης ως αναγνωσμένη"""
    user_id = session['user_id']
    
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if notification:
        notification.is_read = True
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Η ειδοποίηση δεν βρέθηκε'})

@app.route('/api/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Σήμανση όλων των ειδοποιήσεων ως αναγνωσμένες"""
    user_id = session['user_id']
    
    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).all()
    for notification in notifications:
        notification.is_read = True
    
    db.session.commit()
    return jsonify({'success': True})

def create_notification(user_id, title, message, notification_type='info'):
    """Helper function για δημιουργία ειδοποίησης"""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=notification_type
    )
    db.session.add(notification)
    db.session.commit()
    return notification

# ======================== MAIN ROUTES ========================

@app.route('/dashboard')
@login_required
def dashboard():
    """Κεντρικό μενού μετά το login"""
    user = User.query.get(session['user_id'])
    
    # Στατιστικά για το dashboard
    total_violations = Violation.query.count()
    my_violations = Violation.query.filter_by(officer_id=user.id).count()
    
    # Αδιάβαστα μηνύματα
    unread_messages = MessageRecipient.query.filter_by(
        recipient_id=user.id, 
        is_read=False
    ).count()
    
    stats = {
        'total_violations': total_violations,
        'my_violations': my_violations,
        'unread_messages': unread_messages
    }
    
    return render_template('dashboard/central_menu.html', user=user, stats=stats)

@app.route('/new-violation')
@login_required
def new_violation():
    """Φόρμα δημιουργίας νέας παράβασης"""
    user = User.query.get(session['user_id'])
    
    # Λήψη διαθέσιμων χρωμάτων και τύπων οχημάτων
    vehicle_colors = DynamicField.query.filter_by(field_type='vehicle_color', is_active=True).all()
    vehicle_types = DynamicField.query.filter_by(field_type='vehicle_type', is_active=True).all()
    
    # Λήψη παραβάσεων από πίνακα violations_data (με safe query)
    try:
        violations = ViolationsData.query.filter_by(is_active=True).all()
    except:
        # Αν δεν υπάρχει ο πίνακας ή δεν έχει δεδομένα, δημιουργούμε κενή λίστα
        violations = []
    
    return render_template('index.html', 
                         vehicle_colors=vehicle_colors,
                         vehicle_types=vehicle_types, 
                         violations=violations,
                         current_user=user,
                         datetime=datetime)

@app.route('/search')
@login_required 
def search():
    """Σελίδα αναζήτησης παραβάσεων"""
    # Για τώρα ανακατεύθυνση στη λίστα παραβάσεων με search capability
    return redirect(url_for('view_violations'))

@app.route('/statistics')
@login_required
def statistics():
    """Σελίδα στατιστικών"""
    user = User.query.get(session['user_id'])
    
    # Βασικά στατιστικά
    total_violations = Violation.query.count()
    my_violations = Violation.query.filter_by(officer_id=user.id).count()
    
    # Αδιάβαστα μηνύματα (για συμβατότητα με το template)
    unread_messages = MessageRecipient.query.filter_by(
        recipient_id=user.id, 
        is_read=False
    ).count()
    
    # Στατιστικά παραβάσεων
    today_violations = Violation.query.filter(
        Violation.violation_date == datetime.now().date()
    ).count()
    
    this_month_violations = Violation.query.filter(
        Violation.violation_date >= datetime.now().replace(day=1).date()
    ).count()
    
    # Στατιστικά με φωτογραφίες και αφαιρέσεις
    with_photos = Violation.query.filter(Violation.photo_filename != None).count()
    with_removal = Violation.query.filter(Violation.plates_removed == True).count()
    
    stats = {
        'total_violations': total_violations,
        'my_violations': my_violations,
        'unread_messages': unread_messages,
        'today_violations': today_violations,
        'this_month_violations': this_month_violations,
        'with_photos': with_photos,
        'with_removal': with_removal
    }
    
    return render_template('dashboard/central_menu.html', user=user, stats=stats)

@app.route('/violations')
@login_required
def view_violations():
    """Προβολή όλων των παραβάσεων με δυνατότητα αναζήτησης"""
    page = request.args.get('page', 1, type=int)
    search_plate = request.args.get('search_plate', '', type=str).strip()
    per_page = 50  # Αριθμός παραβάσεων ανά σελίδα
    
    # Ξεκινάμε με το βασικό query
    query = Violation.query
    
    # Αν υπάρχει αναζήτηση, φιλτράρουμε
    if search_plate:
        # Αφαιρούμε spaces και dashes για πιο ευέλικτη αναζήτηση
        search_clean = search_plate.replace(' ', '').replace('-', '').upper()
        # Φιλτράρουμε με LIKE pattern για case-insensitive αναζήτηση
        query = query.filter(
            db.func.replace(
                db.func.replace(
                    db.func.upper(Violation.license_plate), ' ', ''
                ), '-', ''
            ).like(f'%{search_clean}%')
        )
    
    # Παίρνουμε τις παραβάσεις με pagination
    violations = query.order_by(Violation.id.desc()).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    # Παίρνουμε τον χρήστη
    user = User.query.get(session['user_id'])
    
    return render_template('violations_list_v2.html', violations=violations, user=user)

@app.route('/violation/<int:violation_id>')
@login_required
def view_violation(violation_id):
    """Προβολή λεπτομερειών παράβασης"""
    violation = Violation.query.get_or_404(violation_id)
    user = User.query.get(session['user_id'])
    
    return render_template('violation_detail.html', violation=violation, user=user)

# ======================== MODULE ROUTES ========================

@app.route('/kok')
@login_required
def kok_module():
    """Μονάδα ΚΟΚ (Κώδικας Οδικής Κυκλοφορίας)"""
    return render_template('modules/kok.html')

@app.route('/elegxos')
@login_required
def elegxos_module():
    """Μονάδα Έλεγχος Καταστημάτων"""
    return render_template('modules/elegxos.html')

@app.route('/epidoseis')
@login_required
def epidoseis_module():
    """Μονάδα Επιδόσεις Εγγράφων"""
    return render_template('modules/epidoseis.html')

@app.route('/anafores')
@login_required
def anafores_module():
    """Μονάδα Αναφορές/Καταγγελίες"""
    return render_template('modules/anafores.html')

# ======================== MESSAGING SYSTEM ========================

@app.route('/messages')
@login_required
def messages_inbox():
    """Εισερχόμενα μηνύματα"""
    user_id = session['user_id']
    
    # Λήψη εισερχόμενων μηνυμάτων
    messages = db.session.query(Message, MessageRecipient)\
        .join(MessageRecipient, Message.id == MessageRecipient.message_id)\
        .filter(MessageRecipient.recipient_id == user_id)\
        .order_by(Message.created_at.desc())\
        .all()
    
    return render_template('messages/inbox.html', messages=messages)

@app.route('/messages/sent')
@login_required
def messages_sent():
    """Απεσταλμένα μηνύματα"""
    user_id = session['user_id']
    
    messages = Message.query.filter_by(sender_id=user_id)\
        .order_by(Message.created_at.desc())\
        .all()
    
    return render_template('messages/sent.html', messages=messages)

@app.route('/messages/new', methods=['GET', 'POST'])
@login_required
def new_message():
    """Σύνθεση νέου μηνύματος"""
    if request.method == 'POST':
        subject = request.form['subject']
        content = request.form['content']
        recipient_ids = request.form.getlist('recipients')
        
        if not recipient_ids:
            flash('Παρακαλώ επιλέξτε τουλάχιστον έναν παραλήπτη.', 'warning')
            return redirect(url_for('new_message'))
        
        # Δημιουργία μηνύματος
        message = Message(
            sender_id=session['user_id'],
            subject=subject,
            content=content,
            is_mass_message=len(recipient_ids) > 1
        )
        db.session.add(message)
        db.session.flush()  # Για να πάρουμε το message_id
        
        # Προσθήκη παραληπτών
        for recipient_id in recipient_ids:
            recipient = MessageRecipient(
                message_id=message.id,
                recipient_id=int(recipient_id)
            )
            db.session.add(recipient)
        
        db.session.commit()
        flash('Το μήνυμα στάλθηκε επιτυχώς!', 'success')
        return redirect(url_for('messages_sent'))
    
    # Λήψη διαθέσιμων παραληπτών
    current_user = User.query.get(session['user_id'])
    recipients = User.query.filter(
        User.id != session['user_id'],
        User.is_active == True
    ).all()
    
    return render_template('messages/new_message.html', 
                         recipients=recipients, 
                         current_user=current_user)

@app.route('/messages/<int:message_id>')
@login_required
def view_message(message_id):
    """Προβολή μηνύματος"""
    user_id = session['user_id']
    
    # Έλεγχος αν ο χρήστης είναι παραλήπτης ή αποστολέας
    message_recipient = MessageRecipient.query.filter_by(
        message_id=message_id,
        recipient_id=user_id
    ).first()
    
    message = Message.query.get_or_404(message_id)
    
    if not message_recipient and message.sender_id != user_id:
        flash('Δεν έχετε δικαίωμα προβολής αυτού του μηνύματος.', 'danger')
        return redirect(url_for('messages_inbox'))
    
    # Σήμανση ως διαβασμένο αν είναι παραλήπτης
    if message_recipient and not message_recipient.is_read:
        message_recipient.is_read = True
        message_recipient.read_at = datetime.utcnow()
        db.session.commit()
    
    return render_template('messages/view_message.html', 
                         message=message, 
                         message_recipient=message_recipient)

# ======================== ADMIN ROUTES ========================

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin Dashboard"""
    # Στατιστικά
    total_users = User.query.count()
    total_violations = Violation.query.count()
    total_messages = Message.query.count()
    
    # Πρόσφατες δραστηριότητες
    recent_violations = Violation.query.order_by(Violation.created_at.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    stats = {
        'total_users': total_users,
        'total_violations': total_violations,
        'total_messages': total_messages
    }
    
    return render_template('admin/dashboard.html', 
                         stats=stats,
                         recent_violations=recent_violations,
                         recent_users=recent_users)

@app.route('/admin/users')
@admin_required
def admin_users():
    """Διαχείριση χρηστών"""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users_enhanced.html', users=users)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    """Προσθήκη νέου χρήστη"""
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        rank = request.form['rank']
        role = request.form['role']  # Νέο πεδίο ρόλου
        
        # Έλεγχος αν υπάρχει ήδη χρήστης με το ίδιο username ή email
        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing_user:
            flash('Υπάρχει ήδη χρήστης με αυτό το όνομα χρήστη ή email.', 'danger')
        else:
            user = User(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                rank=rank,
                role=role
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            flash(f'Ο χρήστης {user.full_name} δημιουργήθηκε επιτυχώς!', 'success')
            return redirect(url_for('admin_users'))
    
    return render_template('admin/add_user_enhanced.html')

@app.route('/admin/violations')
@login_required
@admin_required
def admin_violations():
    """Διαχείριση εκθέσεων παραβάσεων"""
    return render_template('admin/violations.html')

@app.route('/admin/violation-types')
@login_required
@admin_required
def admin_violation_types():
    """Διαχείριση τύπων παραβάσεων ΚΟΚ"""
    violations = ViolationsData.query.filter_by(is_active=True).order_by(ViolationsData.description).all()
    return render_template('admin/violation_types.html', violations=violations)

@app.route('/admin/violation-types/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_violation_types_new():
    """Νέος τύπος παράβασης ΚΟΚ"""
    if request.method == 'POST':
        try:
            # Δημιουργία νέας παράβασης
            violation = ViolationsData(
                description=request.form.get('description'),
                paragraph=request.form.get('paragraph'),
                article=request.form.get('article'),
                article_paragraph=request.form.get('article_paragraph'),
                fine_cars=float(request.form.get('fine_cars', 0)),
                fine_motorcycles=float(request.form.get('fine_motorcycles', 0)) if request.form.get('fine_motorcycles') else None,
                fine_trucks=float(request.form.get('fine_trucks', 0)) if request.form.get('fine_trucks') else None,
                half_fine_motorcycles=bool(request.form.get('half_fine_motorcycles')),
                remove_circulation_elements=bool(request.form.get('remove_circulation_elements')),
                circulation_removal_days=int(request.form.get('circulation_removal_days')) if request.form.get('circulation_removal_days') else None,
                remove_circulation_license=bool(request.form.get('remove_circulation_license')),
                circulation_license_removal_days=int(request.form.get('circulation_license_removal_days')) if request.form.get('circulation_license_removal_days') else None,
                remove_driving_license=bool(request.form.get('remove_driving_license')),
                driving_license_removal_days=int(request.form.get('driving_license_removal_days')) if request.form.get('driving_license_removal_days') else None,
                parking_special_provision=bool(request.form.get('parking_special_provision'))
            )
            
            db.session.add(violation)
            db.session.commit()
            
            flash(f'Ο τύπος παράβασης "{violation.description}" προστέθηκε επιτυχώς!', 'success')
            return redirect(url_for('admin_violation_types'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Σφάλμα κατά την προσθήκη τύπου παράβασης: {str(e)}', 'error')
    
    return render_template('admin/violation_types_form.html', action='new')

@app.route('/admin/violation-types/edit/<int:violation_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_violation_types_edit(violation_id):
    """Επεξεργασία τύπου παράβασης ΚΟΚ"""
    violation = ViolationsData.query.get_or_404(violation_id)
    
    if request.method == 'POST':
        try:
            # Ενημέρωση παράβασης
            violation.description = request.form.get('description')
            violation.paragraph = request.form.get('paragraph')
            violation.article = request.form.get('article')
            violation.article_paragraph = request.form.get('article_paragraph')
            violation.fine_cars = float(request.form.get('fine_cars', 0))
            violation.fine_motorcycles = float(request.form.get('fine_motorcycles', 0)) if request.form.get('fine_motorcycles') else None
            violation.fine_trucks = float(request.form.get('fine_trucks', 0)) if request.form.get('fine_trucks') else None
            violation.half_fine_motorcycles = bool(request.form.get('half_fine_motorcycles'))
            violation.remove_circulation_elements = bool(request.form.get('remove_circulation_elements'))
            violation.circulation_removal_days = int(request.form.get('circulation_removal_days')) if request.form.get('circulation_removal_days') else None
            violation.remove_circulation_license = bool(request.form.get('remove_circulation_license'))
            violation.circulation_license_removal_days = int(request.form.get('circulation_license_removal_days')) if request.form.get('circulation_license_removal_days') else None
            violation.remove_driving_license = bool(request.form.get('remove_driving_license'))
            violation.driving_license_removal_days = int(request.form.get('driving_license_removal_days')) if request.form.get('driving_license_removal_days') else None
            violation.parking_special_provision = bool(request.form.get('parking_special_provision'))
            violation.updated_at = datetime.now()
            
            db.session.commit()
            
            flash(f'Ο τύπος παράβασης "{violation.description}" ενημερώθηκε επιτυχώς!', 'success')
            return redirect(url_for('admin_violation_types'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Σφάλμα κατά την ενημέρωση τύπου παράβασης: {str(e)}', 'error')
    
    return render_template('admin/violation_types_form.html', action='edit', violation=violation)

@app.route('/admin/violation-types/delete/<int:violation_id>', methods=['POST'])
@login_required
@admin_required
def admin_violation_types_delete(violation_id):
    """Διαγραφή τύπου παράβασης ΚΟΚ (soft delete)"""
    violation = ViolationsData.query.get_or_404(violation_id)
    
    try:
        # Soft delete - απλά το κάνουμε inactive
        violation.is_active = False
        violation.updated_at = datetime.now()
        db.session.commit()
        
        flash(f'Ο τύπος παράβασης "{violation.description}" διαγράφηκε επιτυχώς!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Σφάλμα κατά τη διαγραφή τύπου παράβασης: {str(e)}', 'error')
    
    return redirect(url_for('admin_violation_types'))

@app.route('/admin/reports') 
@login_required
@admin_required
def admin_reports():
    """Αναφορές και στατιστικά"""
    return render_template('admin/reports.html')

# ======================== MISSING ROUTES FIX ========================

@app.route('/violations/new', methods=['GET', 'POST'])
@login_required
def violations_new():
    """Νέα παράβαση"""
    return redirect(url_for('new_violation'))

@app.route('/violations/search')
@login_required
def violations_search():
    """Αναζήτηση παραβάσεων"""
    return redirect(url_for('view_violations'))

@app.route('/api/search_license_plate', methods=['POST'])
@login_required
def search_license_plate():
    """API endpoint για αναζήτηση πινακίδας και αυτόματη συμπλήρωση πεδίων"""
    try:
        data = request.get_json()
        license_plate = data.get('license_plate', '').strip().upper()
        
        if not license_plate:
            return jsonify({'success': False, 'message': 'Δεν δόθηκε πινακίδα'})
        
        # Αναζήτηση της πιο πρόσφατης παράβασης για αυτή την πινακίδα
        violation = Violation.query.filter_by(license_plate=license_plate)\
                                 .order_by(Violation.created_at.desc())\
                                 .first()
        
        if violation:
            return jsonify({
                'success': True,
                'found': True,
                'data': {
                    'vehicle_brand': violation.vehicle_brand,
                    'vehicle_color': violation.vehicle_color, 
                    'vehicle_type': violation.vehicle_type
                },
                'message': f'Βρέθηκαν στοιχεία για την πινακίδα {license_plate}'
            })
        else:
            return jsonify({
                'success': True,
                'found': False,
                'message': f'Δεν βρέθηκαν στοιχεία για την πινακίδα {license_plate}'
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Σφάλμα: {str(e)}'})

@app.route('/violations/stats')
@login_required
def violations_stats():
    """Στατιστικά παραβάσεων"""
    try:
        user = User.query.get(session['user_id'])
        if not user:
            flash('Σφάλμα: Χρήστης δεν βρέθηκε', 'error')
            return redirect(url_for('dashboard'))
        
        # Βασικά στατιστικά
        stats = {}
        stats['total_violations'] = Violation.query.count() or 0
        
        # Date statistics με ασφαλή τρόπο
        from datetime import date
        today = date.today()
        month_start = today.replace(day=1)
        
        # Στατιστικά ημέρας (χρήση string comparison αντί για func.date)
        stats['today_violations'] = Violation.query.filter(
            Violation.violation_date == today
        ).count() or 0
        
        # Στατιστικά μήνα
        stats['month_violations'] = Violation.query.filter(
            Violation.violation_date >= month_start
        ).count() or 0
        
        stats['violations_with_photos'] = Violation.query.filter(Violation.photo_filename != None).count() or 0
        
        # Παραβάσεις με επιτόπια μέτρα (πινακίδες, άδεια, κυκλοφορία)
        stats['violations_with_removals'] = Violation.query.filter(
            or_(
                Violation.plates_removed == True,
                Violation.license_removed == True, 
                Violation.registration_removed == True
            )
        ).count() or 0
        
        # Μη διαβασμένα μηνύματα - διορθώθηκε για συνέπεια
        unread_messages = MessageRecipient.query.filter_by(recipient_id=user.id, is_read=False).count() or 0
        
        return render_template('violations_stats.html', 
                             user=user, 
                             stats=stats, 
                             unread_messages=unread_messages)
    
    except Exception as e:
        flash(f'Σφάλμα στη φόρτωση στατιστικών: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/edit_violation/<int:violation_id>')
@login_required
def edit_violation(violation_id):
    """Φόρμα επεξεργασίας παράβασης - μόνο για admin"""
    user = User.query.get(session['user_id'])
    
    # Έλεγχος αν ο χρήστης μπορεί να επεξεργαστεί παραβάσεις
    if not user.can_manage_users():
        flash('Δεν έχετε δικαίωμα επεξεργασίας παραβάσεων.', 'error')
        return redirect(url_for('view_violations'))
    
    # Λήψη παράβασης
    violation = Violation.query.get_or_404(violation_id)
    
    # Λήψη διαθέσιμων χρωμάτων και τύπων οχημάτων
    vehicle_colors = DynamicField.query.filter_by(field_type='vehicle_color', is_active=True).all()
    vehicle_types = DynamicField.query.filter_by(field_type='vehicle_type', is_active=True).all()
    
    # Λήψη παραβάσεων από πίνακα violations_data
    try:
        violations = ViolationsData.query.filter_by(is_active=True).all()
    except:
        violations = []
    
    return render_template('edit_violation.html', 
                         violation=violation,
                         vehicle_colors=vehicle_colors,
                         vehicle_types=vehicle_types, 
                         violations=violations,
                         current_user=user,
                         datetime=datetime)

@app.route('/update_violation/<int:violation_id>', methods=['POST'])
@login_required
def update_violation(violation_id):
    """Ενημέρωση παράβασης - μόνο για admin"""
    user = User.query.get(session['user_id'])
    
    # Έλεγχος αν ο χρήστης μπορεί να επεξεργαστεί παραβάσεις
    if not user.can_manage_users():
        flash('Δεν έχετε δικαίωμα επεξεργασίας παραβάσεων.', 'error')
        return redirect(url_for('view_violations'))
    
    try:
        # Λήψη παράβασης
        violation = Violation.query.get_or_404(violation_id)
        
        # Λήψη δεδομένων από φόρμα
        license_plate = request.form['license_plate'].strip().upper()
        vehicle_brand = request.form['vehicle_brand'].strip()
        vehicle_color = request.form['vehicle_color'].strip()
        vehicle_type = request.form['vehicle_type'].strip()
        
        # Επεξεργασία custom πεδίων
        if vehicle_color == 'custom':
            vehicle_color = request.form['custom_vehicle_color'].strip()
            # Προσθήκη στη βάση δυναμικών πεδίων
            new_color = DynamicField(
                field_type='vehicle_color',
                value=vehicle_color,
                created_by=session['user_id']
            )
            db.session.add(new_color)
        
        if vehicle_type == 'custom':
            vehicle_type = request.form['custom_vehicle_type'].strip()
            # Προσθήκη στη βάση δυναμικών πεδίων  
            new_type = DynamicField(
                field_type='vehicle_type',
                value=vehicle_type,
                created_by=session['user_id']
            )
            db.session.add(new_type)
        
        # Στοιχεία παράβασης
        violation_date = datetime.strptime(request.form['violation_date'], '%Y-%m-%d').date()
        violation_time = datetime.strptime(request.form['violation_time'], '%H:%M').time()
        street = request.form['street'].strip()
        street_number = request.form['street_number'].strip()
        
        # Επιλεγμένες παραβάσεις
        selected_violations = request.form.getlist('violations')
        if not selected_violations:
            flash('Πρέπει να επιλέξετε τουλάχιστον μία παράβαση.', 'error')
            return redirect(url_for('edit_violation', violation_id=violation_id))
        
        # Επιτόπια μέτρα
        plates_removed = 'plates_removed' in request.form
        license_removed = 'license_removed' in request.form  
        registration_removed = 'registration_removed' in request.form
        
        # Στοιχεία οδηγού (αν υπάρχουν στη φόρμα)
        driver_last_name = request.form.get('driver_last_name', '').strip() or None
        driver_first_name = request.form.get('driver_first_name', '').strip() or None
        driver_father_name = request.form.get('driver_father_name', '').strip() or None
        driver_afm = request.form.get('driver_afm', '').strip() or None
        
        # Ενημέρωση παράβασης
        violation.license_plate = license_plate
        violation.vehicle_brand = vehicle_brand
        violation.vehicle_color = vehicle_color
        violation.vehicle_type = vehicle_type
        violation.violation_date = violation_date
        violation.violation_time = violation_time
        violation.street = street
        violation.street_number = street_number
        violation.selected_violations = json.dumps(selected_violations)
        violation.plates_removed = plates_removed
        violation.license_removed = license_removed
        violation.registration_removed = registration_removed
        
        # Ενημέρωση στοιχείων οδηγού
        violation.driver_last_name = driver_last_name
        violation.driver_first_name = driver_first_name
        violation.driver_father_name = driver_father_name
        violation.driver_afm = driver_afm
        
        violation.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Δημιουργία notification για την επεξεργασία
        create_notification(
            user_id=session['user_id'],
            title="Παράβαση Ενημερώθηκε",
            message=f"Η παράβαση #{violation_id} για το όχημα {license_plate} ενημερώθηκε επιτυχώς.",
            notification_type="info"
        )
        
        flash('Η παράβαση ενημερώθηκε επιτυχώς!', 'success')
        return redirect(url_for('view_violations'))
        
    except Exception as e:
        flash(f'Σφάλμα κατά την ενημέρωση: {str(e)}', 'error')
        return redirect(url_for('edit_violation', violation_id=violation_id))

@app.route('/submit_violation', methods=['POST'])
@login_required
def submit_violation():
    """Υποβολή νέας παράβασης"""
    try:
        # Λήψη δεδομένων από φόρμα
        license_plate = request.form['license_plate'].strip().upper()
        vehicle_brand = request.form['vehicle_brand'].strip()
        vehicle_color = request.form['vehicle_color'].strip()
        vehicle_type = request.form['vehicle_type'].strip()
        
        # Επεξεργασία custom πεδίων
        if vehicle_color == 'custom':
            vehicle_color = request.form['custom_vehicle_color'].strip()
            # Προσθήκη στη βάση δυναμικών πεδίων
            new_color = DynamicField(
                field_type='vehicle_color',
                value=vehicle_color,
                created_by=session['user_id']
            )
            db.session.add(new_color)
        
        if vehicle_type == 'custom':
            vehicle_type = request.form['custom_vehicle_type'].strip()
            # Προσθήκη στη βάση δυναμικών πεδίων  
            new_type = DynamicField(
                field_type='vehicle_type',
                value=vehicle_type,
                created_by=session['user_id']
            )
            db.session.add(new_type)
        
        # Στοιχεία παράβασης - Αυτόματη ημερομηνία/ώρα
        current_datetime = datetime.now()
        violation_date = current_datetime.date()
        violation_time = current_datetime.time()
        street = request.form['street'].strip()
        street_number = request.form['street_number'].strip()
        
        # Επιλεγμένες παραβάσεις
        selected_violations = request.form.getlist('violations')
        if not selected_violations:
            flash('Πρέπει να επιλέξετε τουλάχιστον μία παράβαση.', 'error')
            return redirect(url_for('new_violation'))
        
        # Επιτόπια μέτρα
        plates_removed = 'plates_removed' in request.form
        license_removed = 'license_removed' in request.form  
        registration_removed = 'registration_removed' in request.form
        
        # Δημιουργία παράβασης
        violation = Violation(
            license_plate=license_plate,
            vehicle_brand=vehicle_brand,
            vehicle_color=vehicle_color,
            vehicle_type=vehicle_type,
            violation_date=violation_date,
            violation_time=violation_time,
            street=street,
            street_number=street_number,
            selected_violations=json.dumps(selected_violations),
            plates_removed=plates_removed,
            license_removed=license_removed,
            registration_removed=registration_removed,
            officer_id=session['user_id']
        )
        
        db.session.add(violation)
        db.session.commit()
        
        # Δημιουργία notification για τον χρήστη
        user = User.query.get(session['user_id'])
        create_notification(
            user_id=session['user_id'],
            title="Νέα Παράβαση Καταχωρήθηκε",
            message=f"Η παράβαση για το όχημα {license_plate} καταχωρήθηκε επιτυχώς στη διεύθυνση {street} {street_number}.",
            notification_type="success"
        )
        
        # Αν είναι admin ή poweruser, ενημέρωση και άλλων admins
        if user.role in ['admin', 'poweruser']:
            other_admins = User.query.filter(
                User.role.in_(['admin', 'poweruser']),
                User.id != session['user_id'],
                User.is_active == True
            ).all()
            
            for admin in other_admins:
                create_notification(
                    user_id=admin.id,
                    title="Νέα Παράβαση από Συνάδελφο",
                    message=f"Ο/Η {user.full_name} κατέγραψε νέα παράβαση για το όχημα {license_plate}.",
                    notification_type="info"
                )
        
        flash('Η παράβαση καταχωρήθηκε επιτυχώς!', 'success')
        return redirect(url_for('view_violations'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Σφάλμα κατά την καταχώρηση: {str(e)}', 'error')
        return redirect(url_for('new_violation'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # ⚡ RUN MIGRATION - ΠΡΟΣΩΡΙΝΌ!
        run_migration_if_needed()
        
        # Δημιουργία default admin αν δεν υπάρχει
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@municipal.gr',
                first_name='Admin',
                last_name='User',
                rank='Διοικητής',
                role='admin'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Δημιουργήθηκε default admin user: admin/admin123")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
