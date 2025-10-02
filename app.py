import os
import json
import base64
import logging
from datetime import datetime, timedelta
from functools import wraps
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_
from sqlalchemy.exc import OperationalError, ProgrammingError
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
import io
import secrets

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Ασφαλής διαχείριση SECRET_KEY
secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    # Προειδοποίηση για production
    import logging
    logging.warning("SECRET_KEY δεν βρέθηκε στο environment! Χρήση default key για development μόνο.")
    secret_key = 'dev-key-change-in-production-12345678901234567890'
app.config['SECRET_KEY'] = secret_key

# Security improvements
@app.after_request
def add_security_headers(response):
    """Προσθήκη security headers"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

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
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # 8-hour sessions

# Allowed file extensions for security
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'pdf'}

def allowed_file(filename):
    """Έλεγχος επιτρεπόμενων file extensions"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)

# ======================== DATABASE MODELS ========================

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
        except (json.JSONDecodeError, TypeError, ValueError):
            return []
    
    def get_violation_articles_list(self):
        """Επιστρέφει τα άρθρα παραβάσεων ως λίστα"""
        try:
            return json.loads(self.violation_articles) if self.violation_articles else []
        except (json.JSONDecodeError, TypeError, ValueError):
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
    type = db.Column(db.String(20), default='info')  # 'info', 'warning', 'error', 'success', 'message'
    is_read = db.Column(db.Boolean, default=False)
    related_message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)  # Σύνδεση με μήνυμα
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Σχέσεις
    user = db.relationship('User', backref='notifications', lazy=True)
    related_message = db.relationship('Message', backref='notifications', lazy=True)
    
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
            session['full_name'] = user.full_name
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
            'icon': notification.icon,
            'related_message_id': notification.related_message_id
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

@app.route('/api/unread-messages')
@login_required
def get_unread_messages():
    """API endpoint για λήψη αριθμού μη αναγνωσμένων μηνυμάτων"""
    user_id = session['user_id']
    
    # Υπολογισμός μη αναγνωσμένων μηνυμάτων
    unread_count = MessageRecipient.query.filter_by(recipient_id=user_id, is_read=False).count()
    
    return jsonify({
        'unread_count': unread_count
    })

@app.route('/api/sync-message-notifications', methods=['POST'])
@login_required
def sync_message_notifications():
    """API endpoint για δημιουργία notifications για υπάρχοντα μη αναγνωσμένα μηνύματα"""
    user_id = session['user_id']
    
    # Βρες όλα τα μη αναγνωσμένα μηνύματα που δεν έχουν notification
    unread_messages = db.session.query(Message, MessageRecipient).join(
        MessageRecipient, Message.id == MessageRecipient.message_id
    ).filter(
        MessageRecipient.recipient_id == user_id,
        MessageRecipient.is_read == False
    ).all()
    
    notifications_created = 0
    
    for message, recipient in unread_messages:
        # Έλεγχος αν υπάρχει ήδη notification για αυτό το μήνυμα
        existing_notification = Notification.query.filter_by(
            user_id=user_id,
            related_message_id=message.id
        ).first()
        
        if not existing_notification:
            # Δημιουργία notification
            create_notification(
                user_id=user_id,
                title="Νέο Μήνυμα",
                message=f"Έχετε λάβει νέο μήνυμα από {message.sender.full_name}: {message.subject}",
                notification_type='message',
                related_message_id=message.id
            )
            notifications_created += 1
    
    return jsonify({
        'success': True,
        'notifications_created': notifications_created
    })

def create_notification(user_id, title, message, notification_type='info', related_message_id=None):
    """Helper function για δημιουργία ειδοποίησης"""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=notification_type,
        related_message_id=related_message_id
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
    except (AttributeError, OperationalError, ProgrammingError) as e:
        # Αν δεν υπάρχει ο πίνακας ή δεν έχει δεδομένα, δημιουργούμε κενή λίστα
        logger.warning(f"Πρόβλημα κατά την ανάκτηση παραβάσεων: {str(e)}")
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
        # Ασφαλής καθαρισμός input - μόνο alphanumeric και ελληνικά
        import re
        search_clean = re.sub(r'[^\w\u0370-\u03FF]', '', search_plate).upper()
        
        # Έλεγχος ότι το input δεν είναι κενό μετά τον καθαρισμό
        if search_clean:
            # Χρήση παραμετροποιημένου query για ασφάλεια
            search_pattern = f'%{search_clean}%'
            query = query.filter(
                db.func.replace(
                    db.func.replace(
                        db.func.upper(Violation.license_plate), ' ', ''
                    ), '-', ''
                ).like(search_pattern)
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
    
    return render_template('violation_detail.html', violation=violation, user=user, current_user=user)

# ======================== MODULE ROUTES ========================

@app.route('/kok')
@login_required
def kok_module():
    """Μονάδα ΚΟΚ (Κώδικας Οδικής Κυκλοφορίας)"""
    # Υπολογισμός στατιστικών
    today = datetime.now().date()
    start_of_month = today.replace(day=1)
    
    try:
        stats = {
            'today_violations': Violation.query.filter(
                db.func.date(Violation.violation_date) == today
            ).count(),
            'month_violations': Violation.query.filter(
                Violation.violation_date >= start_of_month
            ).count(),
            'active_violations': Violation.query.filter(
                Violation.fine_amount.isnot(None),
                Violation.is_paid == False
            ).count()
        }
    except Exception as e:
        # Fallback σε περίπτωση σφάλματος
        stats = {
            'today_violations': 0,
            'month_violations': 0,
            'active_violations': 0
        }
    
    return render_template('modules/kok.html', stats=stats)

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
            
            # Δημιουργία ειδοποίησης για το νέο μήνυμα
            sender_name = User.query.get(session['user_id']).full_name
            create_notification(
                user_id=int(recipient_id),
                title="Νέο Μήνυμα",
                message=f"Έχετε λάβει νέο μήνυμα από {sender_name}: {subject}",
                notification_type='message',
                related_message_id=message.id
            )
        
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
        
        # Σήμανση της αντίστοιχης ειδοποίησης ως διαβασμένη
        notification = Notification.query.filter_by(
            user_id=user_id,
            related_message_id=message_id,
            is_read=False
        ).first()
        
        if notification:
            notification.is_read = True
        
        db.session.commit()
    
    return render_template('messages/view_message.html', 
                         message=message, 
                         message_recipient=message_recipient)

# ======================== ADMIN ROUTES ========================

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    """Admin Dashboard"""
    current_user = User.query.get(session['user_id'])
    
    # Στατιστικά
    total_users = User.query.count()
    total_violations = Violation.query.count()
    total_messages = Message.query.count()
    
    # Παραβάσεις σήμερα
    from datetime import date
    today = date.today()
    today_violations = Violation.query.filter(
        db.func.date(Violation.violation_date) == today
    ).count()
    
    # Πρόσφατες δραστηριότητες
    recent_violations = Violation.query.order_by(Violation.created_at.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    stats = {
        'total_users': total_users,
        'total_violations': total_violations,
        'total_messages': total_messages
    }
    
    return render_template('admin/dashboard.html', 
                         current_user=current_user,
                         total_users=total_users,
                         total_violations=total_violations,
                         total_messages=total_messages,
                         today_violations=today_violations,
                         stats=stats,
                         recent_violations=recent_violations,
                         recent_users=recent_users)

@app.route('/admin/users')
@admin_required
def admin_users():
    """Διαχείριση χρηστών"""
    current_user = User.query.get(session['user_id'])
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users, current_user=current_user)

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

@app.route('/admin/fines-management')
@login_required
def admin_fines_management():
    """Διαχείριση Προστίμων - Κεντρική σελίδα"""
    user = User.query.get(session['user_id'])
    if not user or not user.can_view_admin_dashboard():
        flash('Δεν έχετε δικαίωμα πρόσβασης σε αυτή τη σελίδα.', 'error')
        return redirect(url_for('dashboard'))
    
    violations_data = ViolationsData.query.filter_by(is_active=True).order_by(ViolationsData.article, ViolationsData.article_paragraph).all()
    return render_template('admin/fines_management.html', violations_data=violations_data)

@app.route('/admin/fines-management/edit/<int:violation_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_fine(violation_id):
    """Επεξεργασία στοιχείων παράβασης/προστίμου"""
    user = User.query.get(session['user_id'])
    if not user or not user.can_view_admin_dashboard():
        flash('Δεν έχετε δικαίωμα πρόσβασης σε αυτή τη σελίδα.', 'error')
        return redirect(url_for('dashboard'))
        
    violation_data = ViolationsData.query.get_or_404(violation_id)
    
    if request.method == 'POST':
        try:
            # Ενημέρωση όλων των πεδίων
            violation_data.description = request.form.get('description', '').strip()
            violation_data.paragraph = request.form.get('paragraph', '').strip()
            violation_data.article = request.form.get('article', '').strip()
            violation_data.article_paragraph = request.form.get('article_paragraph', '').strip()
            
            # Πρόστιμα
            violation_data.fine_cars = Decimal(request.form.get('fine_cars', '0') or '0')
            violation_data.fine_motorcycles = Decimal(request.form.get('fine_motorcycles', '0') or '0') if request.form.get('fine_motorcycles') else None
            violation_data.fine_trucks = Decimal(request.form.get('fine_trucks', '0') or '0') if request.form.get('fine_trucks') else None
            violation_data.half_fine_motorcycles = 'half_fine_motorcycles' in request.form
            
            # Αφαιρέσεις στοιχείων
            violation_data.remove_circulation_elements = 'remove_circulation_elements' in request.form
            violation_data.circulation_removal_days = int(request.form.get('circulation_removal_days', '0') or '0') if request.form.get('circulation_removal_days') else None
            
            # Αφαιρέσεις άδειας κυκλοφορίας
            violation_data.remove_circulation_license = 'remove_circulation_license' in request.form
            violation_data.circulation_license_removal_days = int(request.form.get('circulation_license_removal_days', '0') or '0') if request.form.get('circulation_license_removal_days') else None
            
            # Αφαιρέσεις άδειας οδήγησης
            violation_data.remove_driving_license = 'remove_driving_license' in request.form
            violation_data.driving_license_removal_days = int(request.form.get('driving_license_removal_days', '0') or '0') if request.form.get('driving_license_removal_days') else None
            
            # Ειδική διάταξη στάθμευσης
            violation_data.parking_special_provision = 'parking_special_provision' in request.form
            
            violation_data.updated_at = datetime.utcnow()
            
            db.session.commit()
            flash('Τα στοιχεία του προστίμου ενημερώθηκαν επιτυχώς!', 'success')
            return redirect(url_for('admin_fines_management'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error updating fine data: {str(e)}', exc_info=True)
            flash(f'Σφάλμα κατά την ενημέρωση: {str(e)}', 'error')
    
    return render_template('admin/edit_fine.html', violation_data=violation_data)

@app.route('/admin/fines-management/new', methods=['GET', 'POST'])
@login_required
def admin_new_fine():
    """Δημιουργία νέου τύπου παράβασης/προστίμου"""
    user = User.query.get(session['user_id'])
    if not user or not user.can_view_admin_dashboard():
        flash('Δεν έχετε δικαίωμα πρόσβασης σε αυτή τη σελίδα.', 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        try:
            new_violation = ViolationsData(
                description=request.form.get('description', '').strip(),
                paragraph=request.form.get('paragraph', '').strip(),
                article=request.form.get('article', '').strip(),
                article_paragraph=request.form.get('article_paragraph', '').strip(),
                fine_cars=Decimal(request.form.get('fine_cars', '0') or '0'),
                fine_motorcycles=Decimal(request.form.get('fine_motorcycles', '0') or '0') if request.form.get('fine_motorcycles') else None,
                fine_trucks=Decimal(request.form.get('fine_trucks', '0') or '0') if request.form.get('fine_trucks') else None,
                half_fine_motorcycles='half_fine_motorcycles' in request.form,
                remove_circulation_elements='remove_circulation_elements' in request.form,
                circulation_removal_days=int(request.form.get('circulation_removal_days', '0') or '0') if request.form.get('circulation_removal_days') else None,
                remove_circulation_license='remove_circulation_license' in request.form,
                circulation_license_removal_days=int(request.form.get('circulation_license_removal_days', '0') or '0') if request.form.get('circulation_license_removal_days') else None,
                remove_driving_license='remove_driving_license' in request.form,
                driving_license_removal_days=int(request.form.get('driving_license_removal_days', '0') or '0') if request.form.get('driving_license_removal_days') else None,
                parking_special_provision='parking_special_provision' in request.form
            )
            
            db.session.add(new_violation)
            db.session.commit()
            flash('Ο νέος τύπος παράβασης δημιουργήθηκε επιτυχώς!', 'success')
            return redirect(url_for('admin_fines_management'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error creating new fine: {str(e)}', exc_info=True)
            flash(f'Σφάλμα κατά τη δημιουργία: {str(e)}', 'error')
    
    return render_template('admin/new_fine.html')

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
    """API endpoint για αναζήτηση πινακίδας και εμφάνιση όλων των παραβάσεων"""
    try:
        data = request.get_json()
        license_plate = data.get('license_plate', '').strip().upper()
        
        if not license_plate:
            return jsonify({'success': False, 'message': 'Δεν δόθηκε πινακίδα'})
        
        # Case-insensitive αναζήτηση όλων των παραβάσεων για αυτή την πινακίδα
        violations = Violation.query.filter(
            Violation.license_plate.ilike(f'%{license_plate}%')
        ).order_by(Violation.created_at.desc()).limit(10).all()
        
        if violations:
            # Πάρε στοιχεία από την πιο πρόσφατη παράβαση για αυτόματη συμπλήρωση
            latest_violation = violations[0]
            
            violations_list = []
            for v in violations:
                # Λήψη στοιχείων χρήστη
                user = User.query.get(v.officer_id)
                officer_name = f"{user.first_name} {user.last_name}" if user else 'Άγνωστος'
                
                # Λήψη στοιχείων επιλεγμένων παραβάσεων
                selected_violations = v.get_selected_violations_list()
                violation_description = ', '.join([str(viol_id) for viol_id in selected_violations]) if selected_violations else 'Άγνωστος τύπος'
                
                violations_list.append({
                    'id': v.id,
                    'violation_date': v.violation_date.strftime('%d/%m/%Y') if v.violation_date else 'Άγνωστη ημερομηνία',
                    'violation_time': v.violation_time.strftime('%H:%M') if v.violation_time else 'Άγνωστη ώρα',
                    'violation_type': violation_description,
                    'officer': officer_name,
                    'fine_amount': str(v.total_fine_amount) if v.total_fine_amount else '0'
                })
            
            return jsonify({
                'success': True,
                'found': True,
                'auto_fill_data': {
                    'vehicle_brand': latest_violation.vehicle_brand,
                    'vehicle_color': latest_violation.vehicle_color, 
                    'vehicle_type': latest_violation.vehicle_type
                },
                'violations': violations_list,
                'total_violations': len(violations_list),
                'message': f'Βρέθηκαν {len(violations_list)} παραβάσεις για την πινακίδα {license_plate}'
            })
        else:
            return jsonify({
                'success': True,
                'found': False,
                'violations': [],
                'total_violations': 0,
                'message': f'Δεν βρέθηκαν παραβάσεις για την πινακίδα {license_plate}'
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
        # Λήψη δεδομένων από φόρμα με validation
        license_plate = request.form.get('license_plate', '').strip().upper()
        vehicle_brand = request.form.get('vehicle_brand', '').strip()
        vehicle_color = request.form.get('vehicle_color', '').strip()
        vehicle_type = request.form.get('vehicle_type', '').strip()
        
        # Basic validation
        if not all([license_plate, vehicle_brand, vehicle_color, vehicle_type]):
            flash('Όλα τα πεδία οχήματος είναι υποχρεωτικά.', 'error')
            return redirect(url_for('new_violation'))
        
        # Validate license plate format (basic check)
        if len(license_plate) < 3 or len(license_plate) > 10:
            flash('Μη έγκυρη πινακίδα κυκλοφορίας.', 'error')
            return redirect(url_for('new_violation'))
        
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
        street = request.form.get('street', '').strip()
        street_number = request.form.get('street_number', '').strip()
        
        # Validation for street information
        if not all([street, street_number]):
            flash('Τα στοιχεία διεύθυνσης είναι υποχρεωτικά.', 'error')
            return redirect(url_for('new_violation'))
        
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
        logger.error(f'Error in submit_violation: {str(e)}', exc_info=True)
        flash(f'Σφάλμα κατά την καταχώρηση: {str(e)}', 'error')
        return redirect(url_for('new_violation'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
