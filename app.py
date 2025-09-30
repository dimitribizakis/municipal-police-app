import os
import json
import base64
from datetime import datetime, timedelta
from functools import wraps
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, render_template_string
from flask_sqlalchemy import SQLAlchemy
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
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///municipal_police_v2.db'
    print("Using SQLite database (Development)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # 8-hour sessions

db = SQLAlchemy(app)

# ======================== DATABASE INITIALIZATION ========================
def initialize_database():
    """Αρχικοποίηση βάσης δεδομένων για production"""
    try:
        with app.app_context():
            # Δημιουργία όλων των πινάκων
            db.create_all()
            print("Database tables created successfully")
            
            # Δημιουργία default admin μόνο αν δεν υπάρχει
            if not User.query.filter_by(username='admin').first():
                create_default_admin()
                print("Default admin user created")
            
            # Δημιουργία default dynamic fields μόνο αν δεν υπάρχουν
            if not DynamicField.query.first():
                create_default_dynamic_fields()
                print("Default dynamic fields created")
                
            db.session.commit()
            print("Database initialization completed successfully")
            
    except Exception as e:
        print(f"Database initialization error: {e}")
        # In case of error, try to rollback
        try:
            db.session.rollback()
        except:
            pass

# ======================== DATABASE MODELS ========================

class User(db.Model):
    """Πίνακας Χρηστών (Δημοτικοί Αστυνομικοί + Admin)"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    rank = db.Column(db.String(50), nullable=False)  # Βαθμός
    role = db.Column(db.String(20), nullable=False, default='officer')  # 'admin' or 'officer'
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Σχέση με παραβάσεις
    violations = db.relationship('Violation', backref='officer', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def full_name(self):
        return f"{self.rank} {self.first_name} {self.last_name}"

class DynamicField(db.Model):
    """Πίνακας Δυναμικών Πεδίων (χρώματα, τύποι οχημάτων)"""
    id = db.Column(db.Integer, primary_key=True)
    field_type = db.Column(db.String(50), nullable=False)  # 'vehicle_color' or 'vehicle_type'
    value = db.Column(db.String(100), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

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
        if not user or user.role != 'admin':
            flash('Δεν έχετε δικαίωμα πρόσβασης σε αυτή τη σελίδα.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ======================== UTILITY FUNCTIONS ========================

def load_violations():
    """Φόρτωση παραβάσεων από JSON αρχείο"""
    try:
        with open('violations.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def get_current_user():
    """Επιστρέφει τον συνδεδεμένο χρήστη"""
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

@app.context_processor
def inject_user():
    """Κάνει διαθέσιμη τη μεταβλητή current_user σε όλα τα templates"""
    return dict(current_user=get_current_user())

def save_uploaded_file(file):
    """Αποθήκευση φωτογραφίας"""
    if file and file.filename:
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
        filename = timestamp + filename
        
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Άνοιγμα και συμπίεση εικόνας
        try:
            image = Image.open(file.stream)
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGB')
            
            # Συμπίεση αν η εικόνα είναι πολύ μεγάλη
            max_size = (1200, 1200)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Αποθήκευση με ποιότητα 85%
            image.save(file_path, 'JPEG', quality=85, optimize=True)
            return filename
        except Exception as e:
            print(f"Error processing image: {e}")
            return None
    return None

# ======================== AUTHENTICATION ROUTES ========================

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Ensure database is initialized for production
    ensure_database_initialized()
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username, is_active=True).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['user_role'] = user.role
            session['full_name'] = user.full_name
            session.permanent = True
            
            flash(f'Καλώς ήρθατε, {user.full_name}!', 'success')
            
            # Redirect based on role
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('index'))
        else:
            flash('Λάθος στοιχεία σύνδεσης.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Αποσυνδεθήκατε επιτυχώς.', 'info')
    return redirect(url_for('login'))

# ======================== MAIN APPLICATION ROUTES ========================

@app.route('/')
@login_required
def index():
    """Κεντρική σελίδα - Φόρμα καταχώρησης παράβασης"""
    violations_list = load_violations()
    
    # Φόρτωση δυναμικών πεδίων
    vehicle_colors = DynamicField.query.filter_by(field_type='vehicle_color', is_active=True).all()
    vehicle_types = DynamicField.query.filter_by(field_type='vehicle_type', is_active=True).all()
    
    # Φόρτωση current user για το template
    current_user = get_current_user()
    
    return render_template('index.html', 
                         violations=violations_list,
                         vehicle_colors=vehicle_colors,
                         vehicle_types=vehicle_types,
                         current_user=current_user,
                         datetime=datetime)

@app.route('/submit', methods=['POST'])
@login_required
def submit_violation():
    """Καταχώρηση νέας παράβασης"""
    try:
        # Λήψη δεδομένων φόρμας
        license_plate = request.form.get('license_plate')
        vehicle_brand = request.form.get('vehicle_brand')
        vehicle_color = request.form.get('vehicle_color')
        vehicle_type = request.form.get('vehicle_type')
        
        # Custom χρώμα/τύπος αν υπάρχει
        custom_color = request.form.get('custom_vehicle_color')
        custom_type = request.form.get('custom_vehicle_type')
        
        if custom_color and custom_color.strip():
            vehicle_color = custom_color.strip()
            # Αποθήκευση νέου χρώματος
            existing_color = DynamicField.query.filter_by(
                field_type='vehicle_color', 
                value=vehicle_color
            ).first()
            if not existing_color:
                new_color = DynamicField(
                    field_type='vehicle_color',
                    value=vehicle_color,
                    created_by=session['user_id']
                )
                db.session.add(new_color)
        
        if custom_type and custom_type.strip():
            vehicle_type = custom_type.strip()
            # Αποθήκευση νέου τύπου
            existing_type = DynamicField.query.filter_by(
                field_type='vehicle_type', 
                value=vehicle_type
            ).first()
            if not existing_type:
                new_type = DynamicField(
                    field_type='vehicle_type',
                    value=vehicle_type,
                    created_by=session['user_id']
                )
                db.session.add(new_type)
        
        # Ημερομηνία και ώρα παράβασης (με έλεγχο για None και κενά strings)
        violation_date_str = request.form.get('violation_date')
        violation_time_str = request.form.get('violation_time')
        
        if not violation_date_str or not violation_date_str.strip():
            violation_date = datetime.now().date()
        else:
            violation_date = datetime.strptime(violation_date_str.strip(), '%Y-%m-%d').date()
            
        if not violation_time_str or not violation_time_str.strip():
            violation_time = datetime.now().time()
        else:
            violation_time = datetime.strptime(violation_time_str.strip(), '%H:%M').time()
        street = request.form.get('street')
        street_number = request.form.get('street_number')
        
        # Παραβάσεις (πολλαπλές επιλογές)
        selected_violations = request.form.getlist('violations')
        
        # Επιτόπια μέτρα
        plates_removed = 'plates_removed' in request.form
        license_removed = 'license_removed' in request.form
        registration_removed = 'registration_removed' in request.form
        
        # Φωτογραφία
        photo_filename = None
        photo_data = request.form.get('photo_data')
        if photo_data and photo_data.startswith('data:image'):
            # Save base64 image
            try:
                header, data = photo_data.split(',', 1)
                image_data = base64.b64decode(data)
                image = Image.open(io.BytesIO(image_data))
                
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                photo_filename = f"camera_{timestamp}.jpg"
                
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
                
                # Συμπίεση
                if image.mode in ('RGBA', 'LA', 'P'):
                    image = image.convert('RGB')
                max_size = (1200, 1200)
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                image.save(file_path, 'JPEG', quality=85, optimize=True)
                
            except Exception as e:
                print(f"Error saving camera image: {e}")
        else:
            # Regular file upload
            photo_file = request.files.get('photo_file')
            if photo_file:
                photo_filename = save_uploaded_file(photo_file)
        
        # Στοιχεία οδηγού (μόνο αν είναι παρών)
        driver_present = 'driver_present' in request.form
        
        if driver_present:
            driver_last_name = request.form.get('driver_last_name')
            driver_first_name = request.form.get('driver_first_name')
            driver_father_name = request.form.get('driver_father_name')
            driver_afm = request.form.get('driver_afm')
            driver_signature = request.form.get('signature_data')
            
            # Validation μόνο αν είναι παρών ο οδηγός
            if not all([driver_last_name, driver_first_name, driver_father_name, driver_afm]):
                flash('Παρακαλώ συμπληρώστε όλα τα στοιχεία του οδηγού.', 'error')
                return redirect(url_for('index'))
        else:
            driver_last_name = None
            driver_first_name = None
            driver_father_name = None
            driver_afm = None
            driver_signature = None
        
        # Δημιουργία νέας παράβασης
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
            photo_filename=photo_filename,
            driver_last_name=driver_last_name,
            driver_first_name=driver_first_name,
            driver_father_name=driver_father_name,
            driver_afm=driver_afm,
            driver_signature=driver_signature,
            officer_id=session['user_id']
        )
        
        # Προσθήκη στη βάση δεδομένων
        db.session.add(violation)
        db.session.commit()
        
        flash('Η παράβαση καταχωρήθηκε επιτυχώς!', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Σφάλμα κατά την καταχώρηση: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/violations')
@login_required
def view_violations():
    """Προβολή παραβάσεων"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Αν είναι admin, βλέπει όλες τις παραβάσεις
    # Αν είναι officer, βλέπει μόνο τις δικές του
    current_user = get_current_user()
    
    if current_user.role == 'admin':
        violations = Violation.query.order_by(Violation.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    else:
        violations = Violation.query.filter_by(officer_id=current_user.id).order_by(
            Violation.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('violations_list_v2.html', violations=violations)

@app.route('/violation/<int:violation_id>')
@login_required
def view_violation(violation_id):
    """Προβολή συγκεκριμένης παράβασης"""
    violation = Violation.query.get_or_404(violation_id)
    
    # Έλεγχος δικαιωμάτων
    current_user = get_current_user()
    if current_user.role != 'admin' and violation.officer_id != current_user.id:
        flash('Δεν έχετε δικαίωμα προβολής αυτής της παράβασης.', 'error')
        return redirect(url_for('view_violations'))
    
    violations_list = load_violations()
    selected_violations = violation.get_selected_violations_list()
    
    return render_template('violation_detail.html', 
                         violation=violation, 
                         violations_list=violations_list,
                         selected_violations=selected_violations)

# ======================== ADMIN ROUTES ========================

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin Dashboard"""
    try:
        # Παίρνουμε τον τρέχοντα χρήστη
        current_user = User.query.get(session['user_id'])
        
        # Στατιστικά με try-except για ασφάλεια
        try:
            total_users = User.query.filter_by(is_active=True).count()
        except Exception:
            total_users = 0
            
        try:
            total_violations = Violation.query.count()
        except Exception:
            total_violations = 0
            
        try:
            today_violations = Violation.query.filter(
                Violation.violation_date == datetime.now().date()
            ).count()
        except Exception:
            today_violations = 0
        
        # Πρόσφατες παραβάσεις
        try:
            recent_violations = Violation.query.order_by(
                Violation.created_at.desc()
            ).limit(10).all()
        except Exception:
            recent_violations = []
        
        return render_template('admin/dashboard.html',
                             current_user=current_user,
                             total_users=total_users,
                             total_violations=total_violations,
                             today_violations=today_violations,
                             recent_violations=recent_violations)
    except Exception as e:
        flash(f'Σφάλμα κατά τη φόρτωση dashboard: {str(e)}', 'error')
        return redirect(url_for('login'))

@app.route('/admin/users')
@admin_required
def admin_users():
    """Διαχείριση χρηστών"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    users = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/users.html', users=users)

@app.route('/admin/add_user', methods=['GET', 'POST'])
@admin_required
def admin_add_user():
    """Προσθήκη νέου χρήστη"""
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            rank = request.form.get('rank')
            role = request.form.get('role')
            
            # Έλεγχος αν υπάρχει ήδη
            if User.query.filter_by(username=username).first():
                flash('Το όνομα χρήστη υπάρχει ήδη.', 'error')
                return render_template('admin/add_user.html')
            
            if User.query.filter_by(email=email).first():
                flash('Το email υπάρχει ήδη.', 'error')
                return render_template('admin/add_user.html')
            
            # Δημιουργία νέου χρήστη
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
            
            flash(f'Ο χρήστης {username} δημιουργήθηκε επιτυχώς!', 'success')
            return redirect(url_for('admin_users'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Σφάλμα κατά τη δημιουργία χρήστη: {str(e)}', 'error')
    
    return render_template('admin/add_user.html')

@app.route('/admin/violations')
@admin_required
def admin_violations():
    """Διαχείριση παραβάσεων"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    violations = Violation.query.order_by(Violation.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/violations.html', violations=violations)

@app.route('/admin/edit_violation/<int:violation_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_violation(violation_id):
    """Επεξεργασία παράβασης"""
    violation = Violation.query.get_or_404(violation_id)
    
    if request.method == 'POST':
        try:
            # Ενημέρωση δεδομένων
            violation.license_plate = request.form.get('license_plate')
            violation.vehicle_brand = request.form.get('vehicle_brand')
            violation.vehicle_color = request.form.get('vehicle_color')
            violation.vehicle_type = request.form.get('vehicle_type')
            violation.street = request.form.get('street')
            violation.street_number = request.form.get('street_number')
            
            # Παραβάσεις
            selected_violations = request.form.getlist('violations')
            violation.selected_violations = json.dumps(selected_violations)
            
            # Επιτόπια μέτρα
            violation.plates_removed = 'plates_removed' in request.form
            violation.license_removed = 'license_removed' in request.form
            violation.registration_removed = 'registration_removed' in request.form
            
            violation.updated_at = datetime.utcnow()
            
            db.session.commit()
            flash('Η παράβαση ενημερώθηκε επιτυχώς!', 'success')
            return redirect(url_for('admin_violations'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Σφάλμα κατά την ενημέρωση: {str(e)}', 'error')
    
    violations_list = load_violations()
    vehicle_colors = DynamicField.query.filter_by(field_type='vehicle_color', is_active=True).all()
    vehicle_types = DynamicField.query.filter_by(field_type='vehicle_type', is_active=True).all()
    
    return render_template('admin/edit_violation.html', 
                         violation=violation,
                         violations_list=violations_list,
                         vehicle_colors=vehicle_colors,
                         vehicle_types=vehicle_types)

@app.route('/admin/reports')
@admin_required
def admin_reports():
    """Αναφορές"""
    # Λίστα αστυνομικών για το dropdown
    officers = User.query.filter_by(role='officer', is_active=True).all()
    
    return render_template('admin/reports.html', officers=officers)

@app.route('/admin/generate_report', methods=['POST'])
@admin_required
def admin_generate_report():
    """Δημιουργία αναφοράς"""
    try:
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        report_type = request.form.get('report_type')
        officer_id = request.form.get('officer_id')
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        # Base query
        query = Violation.query.filter(
            Violation.violation_date >= start_date,
            Violation.violation_date <= end_date
        )
        
        # Φίλτρο ανά αστυνομικό
        if officer_id and officer_id != 'all':
            query = query.filter(Violation.officer_id == int(officer_id))
        
        violations = query.order_by(Violation.violation_date.desc()).all()
        
        # Υπολογισμός συνολικού ποσού προστίμων
        total_fine_amount = sum(
            violation.total_fine_amount for violation in violations 
            if violation.total_fine_amount
        )
        
        # Get all officers for the report
        officers = User.query.filter_by(role='officer', is_active=True).all()
        
        report_data = {
            'violations': violations,
            'start_date': start_date,
            'end_date': end_date,
            'report_type': report_type,
            'total_violations': len(violations),
            'total_fine_amount': total_fine_amount,
            'officers': officers,
            'current_datetime': datetime.now()
        }
        
        if officer_id and officer_id != 'all':
            selected_officer = User.query.get(int(officer_id))
            report_data['selected_officer'] = selected_officer
        
        return render_template('admin/report_result.html', **report_data)
        
    except Exception as e:
        flash(f'Σφάλμα κατά τη δημιουργία αναφοράς: {str(e)}', 'error')
        return redirect(url_for('admin_reports'))

# ======================== TEMPORARY MIGRATION ROUTE ========================

@app.route('/admin/migrate-fines')
@admin_required
def migrate_fines():
    """ΠΡΟΣΩΡΙΝΟ ROUTE: Εκτέλεση migration προστίμων - ΔΙΑΓΡΑΦΗ ΜΕΤΑ ΤΗ ΧΡΗΣΗ"""
    try:
        results = []
        results.append("🚀 Έναρξη Migration: Προσθήκη πεδίων προστίμων παραβάσεων")
        results.append("=" * 60)
        
        # Βήμα 1: Προσθήκη νέων στηλών
        results.append("\n📊 Προσθήκη νέων στηλών στη βάση δεδομένων...")
        
        try:
            # Για SQLite (development) - χρήση ALTER TABLE
            if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
                db.session.execute(db.text("ALTER TABLE violation ADD COLUMN violation_articles TEXT"))
                db.session.execute(db.text("ALTER TABLE violation ADD COLUMN total_fine_amount NUMERIC(8,2)"))
                db.session.execute(db.text("ALTER TABLE violation ADD COLUMN fine_breakdown TEXT"))
                results.append("✓ Στήλες προστέθηκαν επιτυχώς (SQLite)")
            else:
                # Για PostgreSQL (production)
                db.session.execute(db.text("ALTER TABLE violation ADD COLUMN IF NOT EXISTS violation_articles TEXT"))
                db.session.execute(db.text("ALTER TABLE violation ADD COLUMN IF NOT EXISTS total_fine_amount NUMERIC(8,2)"))
                db.session.execute(db.text("ALTER TABLE violation ADD COLUMN IF NOT EXISTS fine_breakdown TEXT"))
                results.append("✓ Στήλες προστέθηκαν επιτυχώς (PostgreSQL)")
                
            db.session.commit()
            
        except Exception as e:
            results.append(f"⚠️  Πιθανώς οι στήλες υπάρχουν ήδη ή υπήρξε σφάλμα: {e}")
            db.session.rollback()

        # Βήμα 2: Ενημέρωση υπαρχουσών παραβάσεων
        results.append("\n📝 Ενημέρωση υπαρχουσών παραβάσεων...")
        
        # Φόρτωση δεδομένων παραβάσεων
        violations_data = load_violations()
        results.append(f"Φορτώθηκαν {len(violations_data)} παραβάσεις από violations.json")
        
        # Λήψη όλων των παραβάσεων που δεν έχουν ποσό
        violations = db.session.execute(db.text("""
            SELECT id, selected_violations, vehicle_type 
            FROM violation 
            WHERE total_fine_amount IS NULL OR total_fine_amount = 0
        """)).fetchall()
        
        results.append(f"Βρέθηκαν {len(violations)} παραβάσεις για ενημέρωση")
        
        updated_count = 0
        for violation_row in violations:
            try:
                violation_id = violation_row[0]
                selected_violations_json = violation_row[1]
                vehicle_type = violation_row[2]
                
                # Parse των επιλεγμένων παραβάσεων
                try:
                    selected_violations = json.loads(selected_violations_json)
                except:
                    selected_violations = []
                
                # Υπολογισμός προστίμων - λογική κατευθείαν εδώ
                total_fine = 0.0
                fine_breakdown = []
                violation_articles = []
                
                for violation_index in selected_violations:
                    try:
                        violation_index = int(violation_index)
                        if 0 <= violation_index < len(violations_data):
                            violation_info = violations_data[violation_index]
                            
                            # Υπολογισμός ποσού ανάλογα με τον τύπο οχήματος
                            fine_amount = 0.0
                            
                            # Έλεγχος αν είναι μοτοσικλέτα/μοτοποδήλατο
                            is_motorcycle = any(keyword in vehicle_type.lower() for keyword in 
                                              ['μοτο', 'moto', 'δίκυκλο', 'δικυκλο'])
                            
                            if is_motorcycle and 'fine_motorcycles' in violation_info:
                                fine_amount = float(violation_info['fine_motorcycles'])
                            elif 'fine_cars' in violation_info:
                                fine_amount = float(violation_info['fine_cars'])
                            
                            if fine_amount > 0:
                                total_fine += fine_amount
                                fine_breakdown.append({
                                    'description': violation_info['description'],
                                    'amount': fine_amount
                                })
                                
                                # Προσθήκη άρθρου αν υπάρχει
                                if 'article' in violation_info and violation_info['article']:
                                    violation_articles.append(violation_info['article'])
                            
                    except (ValueError, KeyError, IndexError) as e:
                        continue
                
                # Ενημέρωση στη βάση
                if total_fine > 0:
                    db.session.execute(db.text("""
                        UPDATE violation 
                        SET total_fine_amount = :total_fine,
                            violation_articles = :articles,
                            fine_breakdown = :breakdown
                        WHERE id = :violation_id
                    """), {
                        'total_fine': total_fine,
                        'articles': json.dumps(violation_articles),
                        'breakdown': json.dumps(fine_breakdown),
                        'violation_id': violation_id
                    })
                    
                    updated_count += 1
                    results.append(f"✓ Παράβαση #{violation_id}: {total_fine}€ για {vehicle_type}")
                
            except Exception as e:
                results.append(f"⚠️  Σφάλμα στην ενημέρωση παράβασης #{violation_id}: {e}")
                continue
        
        # Commit όλων των αλλαγών
        try:
            db.session.commit()
            results.append(f"\n✅ Ενημερώθηκαν επιτυχώς {updated_count} παραβάσεις")
        except Exception as e:
            db.session.rollback()
            results.append(f"\n❌ Σφάλμα κατά την αποθήκευση: {e}")
            return render_template_string("""
                <h1>❌ Migration Απέτυχε</h1>
                <pre>{{ results|join('\n') }}</pre>
                <a href="{{ url_for('admin_dashboard') }}">Επιστροφή στο Admin</a>
            """, results=results)

        # Βήμα 3: Επαλήθευση
        results.append("\n🔍 Επαλήθευση migration...")
        
        try:
            # Στατιστικά
            total_violations = db.session.execute(db.text("SELECT COUNT(*) FROM violation")).scalar()
            violations_with_fines = db.session.execute(db.text(
                "SELECT COUNT(*) FROM violation WHERE total_fine_amount > 0"
            )).scalar()
            
            results.append(f"📊 Στατιστικά:")
            results.append(f"   - Συνολικές παραβάσεις: {total_violations}")
            results.append(f"   - Παραβάσεις με ποσά: {violations_with_fines}")
            
            if total_violations > 0:
                percentage = (violations_with_fines/total_violations)*100
                results.append(f"   - Ποσοστό ολοκλήρωσης: {percentage:.1f}%")
            
            results.append("\n🎉 Migration ολοκληρώθηκε επιτυχώς!")
            results.append("Τώρα όλες οι παραβάσεις περιλαμβάνουν άρθρα και ποσά προστίμων.")
            
        except Exception as e:
            results.append(f"❌ Σφάλμα στην επαλήθευση: {e}")
        
        return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Migration Αποτελέσματα</title>
                <meta charset="utf-8">
                <style>
                    body { font-family: monospace; margin: 20px; background: #f5f5f5; }
                    .container { background: white; padding: 20px; border-radius: 8px; }
                    pre { background: #f8f8f8; padding: 15px; border-radius: 4px; overflow-x: auto; }
                    .success { color: #28a745; }
                    .warning { color: #ffc107; }
                    .error { color: #dc3545; }
                    .button { 
                        display: inline-block; 
                        padding: 10px 20px; 
                        margin: 20px 5px 0 0;
                        background: #007bff; 
                        color: white; 
                        text-decoration: none; 
                        border-radius: 4px; 
                    }
                    .button:hover { background: #0056b3; }
                    .delete-btn { background: #dc3545; }
                    .delete-btn:hover { background: #c82333; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🚀 Migration Αποτελέσματα</h1>
                    <pre>{{ results|join('\n') }}</pre>
                    
                    <div style="margin-top: 20px; padding: 15px; background: #fff3cd; border-radius: 4px;">
                        <strong>⚠️ ΣΗΜΑΝΤΙΚΟ:</strong> Αυτό το route είναι προσωρινό και πρέπει να <strong>διαγραφεί</strong> 
                        μετά την επιτυχή εκτέλεση του migration!
                    </div>
                    
                    <a href="{{ url_for('admin_dashboard') }}" class="button">✓ Επιστροφή στο Admin</a>
                    <a href="{{ url_for('view_violations') }}" class="button">📋 Δες Παραβάσεις</a>
                </div>
            </body>
            </html>
        """, results=results)
        
    except Exception as e:
        error_msg = f"💥 Κρίσιμο σφάλμα migration: {str(e)}"
        return render_template_string("""
            <h1>❌ Migration Απέτυχε</h1>
            <pre>{{ error_msg }}</pre>
            <a href="{{ url_for('admin_dashboard') }}">Επιστροφή στο Admin</a>
        """, error_msg=error_msg)

# ======================== API ROUTES ========================

@app.route('/api/dynamic_fields/<field_type>')
@login_required
def api_get_dynamic_fields(field_type):
    """API για λήψη δυναμικών πεδίων"""
    fields = DynamicField.query.filter_by(
        field_type=field_type, 
        is_active=True
    ).order_by(DynamicField.value).all()
    
    return jsonify([{'id': f.id, 'value': f.value} for f in fields])

@app.route('/api/officers')
@admin_required
def api_get_officers():
    """API για λήψη αστυνομικών για reports"""
    officers = User.query.filter_by(role='officer', is_active=True).all()
    
    return jsonify([{
        'id': officer.id, 
        'full_name': f"{officer.first_name} {officer.last_name}"
    } for officer in officers])

# ======================== INITIALIZATION ========================

def create_default_admin():
    """Δημιουργία default admin χρήστη"""
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@municipality.gr',
            first_name='Admin',
            last_name='System',
            rank='Διευθυντής',
            role='admin'
        )
        admin.set_password('admin123')  # Change this!
        db.session.add(admin)
        db.session.commit()
        print("Default admin user created: admin/admin123")

def create_default_dynamic_fields():
    """Δημιουργία default δυναμικών πεδίων"""
    # Default χρώματα
    default_colors = ['Λευκό', 'Μαύρο', 'Κόκκινο', 'Μπλε', 'Γκρι', 'Ασημί', 'Πράσινο', 'Καφέ']
    for color in default_colors:
        existing = DynamicField.query.filter_by(field_type='vehicle_color', value=color).first()
        if not existing:
            field = DynamicField(
                field_type='vehicle_color',
                value=color,
                created_by=1  # Admin user
            )
            db.session.add(field)
    
    # Default τύποι οχημάτων
    default_types = ['ΙΧΕ', 'ΦΙΧ', 'ΜΟΤΟ', 'ΜΟΤΑ', 'ΤΑΧΙ', 'ΛΕΩΦΟΡΕΙΟ', 'ΦΟΡΤΗΓΟ']
    for vehicle_type in default_types:
        existing = DynamicField.query.filter_by(field_type='vehicle_type', value=vehicle_type).first()
        if not existing:
            field = DynamicField(
                field_type='vehicle_type',
                value=vehicle_type,
                created_by=1  # Admin user
            )
            db.session.add(field)
    
    db.session.commit()

# ======================== LAZY DATABASE INITIALIZATION ========================
_db_initialized = False

def ensure_database_initialized():
    """Safe database initialization - καλείται όταν χρειάζεται"""
    global _db_initialized
    if not _db_initialized and __name__ != '__main__':  # Production mode only
        try:
            initialize_database()
            _db_initialized = True
        except Exception as e:
            print(f"Database initialization failed: {e}")

if __name__ == '__main__':
    # Development mode
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            create_default_admin()
        if not DynamicField.query.first():
            create_default_dynamic_fields()
    
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
