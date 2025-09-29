import os
import json
import base64
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from PIL import Image
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'municipal_police_app_2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///violations.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Δημιουργία φακέλου για uploads
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static', exist_ok=True)

db = SQLAlchemy(app)

# Custom template filter για JSON
@app.template_filter('from_json')
def from_json(value):
    try:
        return json.loads(value) if value else []
    except:
        return []

# Model για παραβάσεις
class Violation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Στοιχεία οχήματος
    license_plate = db.Column(db.String(20), nullable=False)
    vehicle_brand = db.Column(db.String(50), nullable=False)
    vehicle_color = db.Column(db.String(30), nullable=False)
    vehicle_type = db.Column(db.String(10), nullable=False)  # ΙΧΕ, ΦΙΧ, ΜΟΤΟ, ΜΟΤΑ, ΤΑΧΙ
    
    # Στοιχεία παράβασης
    violation_time = db.Column(db.DateTime, nullable=False)
    street_name = db.Column(db.String(100), nullable=False)
    street_number = db.Column(db.String(20), nullable=False)
    violation_codes = db.Column(db.Text, nullable=False)  # JSON string με τις παραβάσεις
    
    # Αφαιρέσεις στοιχείων
    plates_removed = db.Column(db.Boolean, default=False)
    license_removed = db.Column(db.Boolean, default=False)
    vehicle_license_removed = db.Column(db.Boolean, default=False)
    
    # Φωτογραφία
    photo_filename = db.Column(db.String(100), nullable=True)
    
    # Στοιχεία οδηγού
    driver_lastname = db.Column(db.String(50), nullable=True)
    driver_firstname = db.Column(db.String(50), nullable=True)
    driver_fathername = db.Column(db.String(50), nullable=True)
    driver_tax_number = db.Column(db.String(20), nullable=True)
    
    # Υπογραφή (base64 encoded)
    signature = db.Column(db.Text, nullable=True)
    
    # Μεταδεδομένα
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    officer_name = db.Column(db.String(100), nullable=True)

# Φόρτωση παραβάσεων από JSON
def load_violations():
    try:
        with open('violations.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

@app.route('/')
def index():
    violations_list = load_violations()
    return render_template('index.html', violations=violations_list)

@app.route('/submit_violation', methods=['POST'])
def submit_violation():
    try:
        # Δημιουργία νέας παράβασης
        violation = Violation()
        
        # Στοιχεία οχήματος
        violation.license_plate = request.form.get('license_plate', '').upper()
        violation.vehicle_brand = request.form.get('vehicle_brand', '')
        violation.vehicle_color = request.form.get('vehicle_color', '')
        violation.vehicle_type = request.form.get('vehicle_type', '')
        
        # Στοιχεία παράβασης
        violation_datetime = request.form.get('violation_datetime')
        if violation_datetime:
            violation.violation_time = datetime.fromisoformat(violation_datetime)
        else:
            violation.violation_time = datetime.now()
            
        violation.street_name = request.form.get('street_name', '')
        violation.street_number = request.form.get('street_number', '')
        
        # Παραβάσεις (πολλαπλές επιλογές)
        selected_violations = request.form.getlist('violations')
        violation.violation_codes = json.dumps(selected_violations, ensure_ascii=False)
        
        # Αφαιρέσεις στοιχείων
        violation.plates_removed = 'plates_removed' in request.form
        violation.license_removed = 'license_removed' in request.form
        violation.vehicle_license_removed = 'vehicle_license_removed' in request.form
        
        # Στοιχεία οδηγού
        violation.driver_lastname = request.form.get('driver_lastname', '')
        violation.driver_firstname = request.form.get('driver_firstname', '')
        violation.driver_fathername = request.form.get('driver_fathername', '')
        violation.driver_tax_number = request.form.get('driver_tax_number', '')
        violation.officer_name = request.form.get('officer_name', '')
        
        # Υπογραφή
        signature_data = request.form.get('signature')
        if signature_data and signature_data != 'data:,':
            violation.signature = signature_data
        
        # Φωτογραφία
        if 'vehicle_photo' in request.files:
            file = request.files['vehicle_photo']
            if file and file.filename != '':
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                # Μικρή επεξεργασία εικόνας (resize για εξοικονόμηση χώρου)
                image = Image.open(file.stream)
                image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                image.save(file_path, quality=85, optimize=True)
                
                violation.photo_filename = filename
        
        # Αποθήκευση στη βάση
        db.session.add(violation)
        db.session.commit()
        
        flash('Η παράβαση καταχωρήθηκε επιτυχώς!', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash(f'Σφάλμα κατά την καταχώρηση: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/violations')
def view_violations():
    """Προβολή όλων των καταχωρημένων παραβάσεων"""
    violations = Violation.query.order_by(Violation.created_at.desc()).all()
    return render_template('violations_list.html', violations=violations)

@app.route('/violation/<int:violation_id>')
def view_violation(violation_id):
    """Προβολή συγκεκριμένης παράβασης"""
    violation = Violation.query.get_or_404(violation_id)
    violations_list = load_violations()
    
    # Αποκωδικοποίηση των παραβάσεων
    selected_violations = json.loads(violation.violation_codes) if violation.violation_codes else []
    
    return render_template('violation_detail.html', 
                         violation=violation, 
                         violations_list=violations_list,
                         selected_violations=selected_violations)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)