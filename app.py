import os
import json
import base64
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
import io
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///municipal_police_v2.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # 8-hour sessions

db = SQLAlchemy(app)

# ======================== DATABASE INITIALIZATION ========================
def initialize_database():
    """Αρχικοποίηση βάσης δεδομένων για production"""
    try:
        # Δημιουργία όλων των πινάκων
        db.create_all()
        
        # Δημιουργία default admin μόνο αν δεν υπάρχει
        if not User.query.filter_by(username='admin').first():
            create_default_admin()
        
        # Δημιουργία default dynamic fields μόνο αν δεν υπάρχουν
        if not DynamicField.query.first():
            create_default_dynamic_fields()
            
    except Exception as e:
        print(f"Database initialization error: {e}")

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
    
    # Στοιχεία Οδηγού
    driver_last_name = db.Column(db.String(50), nullable=False)
    driver_first_name = db.Column(db.String(50), nullable=False)
    driver_father_name = db.Column(db.String(50), nullable=False)
    driver_afm = db.Column(db.String(20), nullable=False)
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
    
    return render_template('index.html', 
                         violations=violations_list,
                         vehicle_colors=vehicle_colors,
                         vehicle_types=vehicle_types,
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
        
        # Στοιχεία οδηγού
        driver_last_name = request.form.get('driver_last_name')
        driver_first_name = request.form.get('driver_first_name')
        driver_father_name = request.form.get('driver_father_name')
        driver_afm = request.form.get('driver_afm')
        driver_signature = request.form.get('signature_data')
        
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
    
    return render_template('violations_list.html', violations=violations)

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
    # Στατιστικά
    total_users = User.query.filter_by(is_active=True).count()
    total_violations = Violation.query.count()
    today_violations = Violation.query.filter(
        Violation.violation_date == datetime.now().date()
    ).count()
    
    # Πρόσφατες παραβάσεις
    recent_violations = Violation.query.order_by(
        Violation.created_at.desc()
    ).limit(10).all()
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_violations=total_violations,
                         today_violations=today_violations,
                         recent_violations=recent_violations)

@app.route('/admin/users')
@admin_required
def admin_users():
    """Διαχείριση Χρηστών"""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/add', methods=['GET', 'POST'])
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
            role = request.form.get('role', 'officer')
            
            # Έλεγχος αν υπάρχει ήδη το username ή email
            existing_user = User.query.filter(
                (User.username == username) | (User.email == email)
            ).first()
            
            if existing_user:
                flash('Το όνομα χρήστη ή email υπάρχει ήδη.', 'error')
                return redirect(url_for('admin_add_user'))
            
            # Δημιουργία νέου χρήστη
            new_user = User(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                rank=rank,
                role=role
            )
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.commit()
            
            flash(f'Ο χρήστης {new_user.full_name} δημιουργήθηκε επιτυχώς!', 'success')
            return redirect(url_for('admin_users'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Σφάλμα κατά τη δημιουργία χρήστη: {str(e)}', 'error')
    
    return render_template('admin/add_user.html')

@app.route('/admin/violations')
@admin_required
def admin_violations():
    """Admin - Όλες οι παραβάσεις"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    violations = Violation.query.order_by(Violation.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/violations.html', violations=violations)

@app.route('/admin/violation/<int:violation_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_violation(violation_id):
    """Admin - Επεξεργασία παράβασης"""
    violation = Violation.query.get_or_404(violation_id)
    
    if request.method == 'POST':
        try:
            # Update all fields
            violation.license_plate = request.form.get('license_plate')
            violation.vehicle_brand = request.form.get('vehicle_brand')
            violation.vehicle_color = request.form.get('vehicle_color')
            violation.vehicle_type = request.form.get('vehicle_type')
            
            # Ημερομηνία και ώρα παράβασης (με έλεγχο για None και κενά strings)
            violation_date_str = request.form.get('violation_date')
            violation_time_str = request.form.get('violation_time')
            
            if violation_date_str and violation_date_str.strip():
                violation.violation_date = datetime.strptime(violation_date_str.strip(), '%Y-%m-%d').date()
            if violation_time_str and violation_time_str.strip():
                violation.violation_time = datetime.strptime(violation_time_str.strip(), '%H:%M').time()
            
            violation.street = request.form.get('street')
            violation.street_number = request.form.get('street_number')
            
            selected_violations = request.form.getlist('violations')
            violation.selected_violations = json.dumps(selected_violations)
            
            violation.plates_removed = 'plates_removed' in request.form
            violation.license_removed = 'license_removed' in request.form
            violation.registration_removed = 'registration_removed' in request.form
            
            violation.driver_last_name = request.form.get('driver_last_name')
            violation.driver_first_name = request.form.get('driver_first_name')
            violation.driver_father_name = request.form.get('driver_father_name')
            violation.driver_afm = request.form.get('driver_afm')
            
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
    """Admin - Αναφορές και Στατιστικά"""
    return render_template('admin/reports.html')

@app.route('/admin/reports/generate', methods=['POST'])
@admin_required
def admin_generate_report():
    """Admin - Δημιουργία Αναφοράς"""
    report_type = request.form.get('report_type')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    officer_id = request.form.get('officer_id')
    
    try:
        # Έλεγχος για κενά strings στις ημερομηνίες
        if not start_date or not start_date.strip():
            flash('Παρακαλώ επιλέξτε ημερομηνία έναρξης', 'error')
            return redirect(url_for('admin_reports'))
        if not end_date or not end_date.strip():
            flash('Παρακαλώ επιλέξτε ημερομηνία λήξης', 'error')
            return redirect(url_for('admin_reports'))
            
        start_date = datetime.strptime(start_date.strip(), '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date.strip(), '%Y-%m-%d').date()
        
        # Base query
        query = Violation.query.filter(
            Violation.violation_date >= start_date,
            Violation.violation_date <= end_date
        )
        
        # Filter by officer if specified
        if officer_id and officer_id != 'all':
            query = query.filter(Violation.officer_id == int(officer_id))
        
        violations = query.order_by(Violation.violation_date.desc()).all()
        
        # Get all officers for the report
        officers = User.query.filter_by(role='officer', is_active=True).all()
        
        report_data = {
            'violations': violations,
            'start_date': start_date,
            'end_date': end_date,
            'report_type': report_type,
            'total_violations': len(violations),
            'officers': officers
        }
        
        if officer_id and officer_id != 'all':
            selected_officer = User.query.get(int(officer_id))
            report_data['selected_officer'] = selected_officer
        
        return render_template('admin/report_result.html', **report_data)
        
    except Exception as e:
        flash(f'Σφάλμα κατά τη δημιουργία αναφοράς: {str(e)}', 'error')
        return redirect(url_for('admin_reports'))

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

# ======================== PRODUCTION INITIALIZATION ========================
# Αρχικοποίηση για production environment (όταν δεν τρέχει __name__ == '__main__')
if __name__ != '__main__':
    with app.app_context():
        initialize_database()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_default_admin()
        create_default_dynamic_fields()
    
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
