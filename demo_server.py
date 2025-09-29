#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import http.server
import socketserver
import json
import os
from urllib.parse import parse_qs
from datetime import datetime
import uuid
import base64

# Απλός HTTP Server για demo
class ViolationHandler(http.server.SimpleHTTPRequestHandler):
    
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(self.get_main_page().encode('utf-8'))
        elif self.path == '/violations':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(self.get_violations_page().encode('utf-8'))
        elif self.path.startswith('/static/'):
            # Serve static files
            try:
                file_path = self.path[1:]  # Remove leading /
                with open(file_path, 'rb') as f:
                    self.send_response(200)
                    if file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
                        self.send_header('Content-type', 'image/jpeg')
                    elif file_path.endswith('.png'):
                        self.send_header('Content-type', 'image/png')
                    elif file_path.endswith('.css'):
                        self.send_header('Content-type', 'text/css')
                    elif file_path.endswith('.js'):
                        self.send_header('Content-type', 'application/javascript')
                    self.end_headers()
                    self.wfile.write(f.read())
            except:
                self.send_error(404)
        else:
            super().do_GET()
    
    def do_POST(self):
        if self.path == '/submit_violation':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            # Save violation (simplified)
            violation_id = str(uuid.uuid4())[:8]
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            success_page = f"""
            <!DOCTYPE html>
            <html lang="el">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Επιτυχής Καταχώρηση</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            </head>
            <body>
                <div class="container mt-5">
                    <div class="alert alert-success text-center">
                        <h2>✅ Επιτυχής Καταχώρηση!</h2>
                        <p>Η παράβαση καταχωρήθηκε με ID: <strong>{violation_id}</strong></p>
                        <a href="/" class="btn btn-primary">Νέα Παράβαση</a>
                        <a href="/violations" class="btn btn-secondary">Προβολή Παραβάσεων</a>
                    </div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(success_page.encode('utf-8'))
    
    def get_main_page(self):
        # Load violations
        try:
            with open('violations.json', 'r', encoding='utf-8') as f:
                violations = json.load(f)
        except:
            violations = []
        
        violations_options = ""
        for v in violations:
            violations_options += f'<option value="{v["code"]}">{v["code"]} - {v["description"]} ({v.get("fine_cars", "0")}€)</option>\n'
        
        return f"""
<!DOCTYPE html>
<html lang="el">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Δημοτική Αστυνομία - Καταχώρηση Παραβάσεων</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body {{ background-color: #f8f9fa; }}
        .header {{ 
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white; padding: 20px 0; margin-bottom: 30px;
        }}
        .logo-container {{ display: flex; align-items: center; gap: 15px; }}
        .police-logo {{ height: 60px; border-radius: 8px; padding: 5px; background-color: rgba(255,255,255,0.1); }}
        .card {{ border: none; box-shadow: 0 0 20px rgba(0,0,0,0.1); border-radius: 15px; margin-bottom: 20px; }}
        .card-header {{ 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border-radius: 15px 15px 0 0 !important; padding: 15px 25px;
        }}
        .btn-primary {{ 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none; border-radius: 10px; padding: 12px 30px; font-weight: 600;
        }}
        .form-control, .form-select {{ border-radius: 10px; border: 2px solid #e9ecef; padding: 12px 15px; }}
    </style>
</head>
<body>
    <!-- Header -->
    <div class="header">
        <div class="container">
            <div class="row align-items-center">
                <div class="col-lg-8">
                    <div class="logo-container">
                        <img src="static/logo.jpg" alt="Λογότυπο Δημοτικής Αστυνομίας" class="police-logo">
                        <div>
                            <h1><i class="fas fa-shield-alt me-2"></i>Δημοτική Αστυνομία</h1>
                            <p class="mb-0">Σύστημα Καταχώρησης Παραβάσεων Οχημάτων</p>
                        </div>
                    </div>
                </div>
                <div class="col-lg-4 text-end">
                    <a href="/" class="btn btn-light me-2"><i class="fas fa-plus me-1"></i>Νέα Παράβαση</a>
                    <a href="/violations" class="btn btn-outline-light"><i class="fas fa-list me-1"></i>Προβολή</a>
                </div>
            </div>
        </div>
    </div>

    <div class="container">
        <form method="POST" action="/submit_violation">
            <!-- Στοιχεία Οχήματος -->
            <div class="card">
                <div class="card-header">
                    <h4><i class="fas fa-car me-2"></i>Στοιχεία Οχήματος</h4>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Αριθμός Κυκλοφορίας *</label>
                            <input type="text" class="form-control" name="license_plate" required placeholder="π.χ. ABC-1234">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Μάρκα Οχήματος *</label>
                            <input type="text" class="form-control" name="vehicle_brand" required placeholder="π.χ. Toyota">
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Χρώμα Οχήματος *</label>
                            <select class="form-select" name="vehicle_color" required>
                                <option value="">Επιλέξτε χρώμα</option>
                                <option value="Άσπρο">Άσπρο</option>
                                <option value="Μαύρο">Μαύρο</option>
                                <option value="Γκρι">Γκρι</option>
                                <option value="Κόκκινο">Κόκκινο</option>
                                <option value="Μπλε">Μπλε</option>
                                <option value="Άλλο">Άλλο</option>
                            </select>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Τύπος Οχήματος *</label>
                            <select class="form-select" name="vehicle_type" required>
                                <option value="">Επιλέξτε τύπο</option>
                                <option value="ΙΧΕ">ΙΧΕ</option>
                                <option value="ΦΙΧ">ΦΙΧ</option>
                                <option value="ΜΟΤΟ">ΜΟΤΟ</option>
                                <option value="ΜΟΤΑ">ΜΟΤΑ</option>
                                <option value="ΤΑΧΙ">ΤΑΧΙ</option>
                            </select>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Στοιχεία Παράβασης -->
            <div class="card">
                <div class="card-header">
                    <h4><i class="fas fa-exclamation-triangle me-2"></i>Στοιχεία Παράβασης</h4>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Ημερομηνία & Ώρα *</label>
                            <input type="datetime-local" class="form-control" name="violation_datetime" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Όνομα Αστυνομικού</label>
                            <input type="text" class="form-control" name="officer_name">
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-8 mb-3">
                            <label class="form-label">Οδός *</label>
                            <input type="text" class="form-control" name="street_name" required>
                        </div>
                        <div class="col-md-4 mb-3">
                            <label class="form-label">Αριθμός</label>
                            <input type="text" class="form-control" name="street_number">
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <label class="form-label">Παραβάσεις *</label>
                        <select class="form-select" name="violations" multiple size="5" required>
                            {violations_options}
                        </select>
                        <small class="form-text text-muted">Κρατήστε Ctrl για πολλαπλές επιλογές</small>
                    </div>
                </div>
            </div>

            <!-- Στοιχεία Οδηγού -->
            <div class="card">
                <div class="card-header">
                    <h4><i class="fas fa-user me-2"></i>Στοιχεία Οδηγού/Παραβάτη</h4>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Επώνυμο</label>
                            <input type="text" class="form-control" name="driver_lastname">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Όνομα</label>
                            <input type="text" class="form-control" name="driver_firstname">
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Όνομα Πατρός</label>
                            <input type="text" class="form-control" name="driver_fathername">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">ΑΦΜ</label>
                            <input type="text" class="form-control" name="driver_tax_number" maxlength="9">
                        </div>
                    </div>
                </div>
            </div>

            <!-- Αφαίρεση Στοιχείων -->
            <div class="card">
                <div class="card-header">
                    <h4><i class="fas fa-clipboard-check me-2"></i>Αφαίρεση Στοιχείων</h4>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-4">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" name="plates_removed">
                                <label class="form-check-label">Αφαίρεση Πινακίδων</label>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" name="license_removed">
                                <label class="form-check-label">Αφαίρεση Άδειας Οδήγησης</label>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" name="vehicle_license_removed">
                                <label class="form-check-label">Αφαίρεση Άδειας Κυκλοφορίας</label>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Υποβολή -->
            <div class="card">
                <div class="card-body text-center">
                    <button type="submit" class="btn btn-primary btn-lg">
                        <i class="fas fa-save me-2"></i>Καταχώρηση Παράβασης
                    </button>
                </div>
            </div>
        </form>
    </div>

    <script>
        // Set current datetime
        document.addEventListener('DOMContentLoaded', function() {{
            const now = new Date();
            const localDateTime = new Date(now - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
            document.querySelector('input[name="violation_datetime"]').value = localDateTime;
        }});
    </script>
</body>
</html>
        """
    
    def get_violations_page(self):
        return """
<!DOCTYPE html>
<html lang="el">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Καταχωρημένες Παραβάσεις</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background-color: #f8f9fa; }
        .header { 
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white; padding: 20px 0; margin-bottom: 30px;
        }
        .logo-container { display: flex; align-items: center; gap: 15px; }
        .police-logo { height: 60px; border-radius: 8px; padding: 5px; background-color: rgba(255,255,255,0.1); }
    </style>
</head>
<body>
    <!-- Header -->
    <div class="header">
        <div class="container">
            <div class="row align-items-center">
                <div class="col-lg-8">
                    <div class="logo-container">
                        <img src="static/logo.jpg" alt="Λογότυπο Δημοτικής Αστυνομίας" class="police-logo">
                        <div>
                            <h1><i class="fas fa-shield-alt me-2"></i>Δημοτική Αστυνομία</h1>
                            <p class="mb-0">Σύστημα Καταχώρησης Παραβάσεων Οχημάτων</p>
                        </div>
                    </div>
                </div>
                <div class="col-lg-4 text-end">
                    <a href="/" class="btn btn-light me-2"><i class="fas fa-plus me-1"></i>Νέα Παράβαση</a>
                    <a href="/violations" class="btn btn-outline-light"><i class="fas fa-list me-1"></i>Προβολή</a>
                </div>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="card">
            <div class="card-header" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;">
                <div class="d-flex align-items-center justify-content-between">
                    <div class="d-flex align-items-center">
                        <img src="static/logo.jpg" alt="Λογότυπο" style="height: 40px; margin-right: 15px; border-radius: 5px;">
                        <h4 class="mb-0"><i class="fas fa-list me-2"></i>Καταχωρημένες Παραβάσεις</h4>
                    </div>
                    <span class="badge bg-light text-dark">Demo Mode</span>
                </div>
            </div>
            <div class="card-body text-center py-5">
                <i class="fas fa-info-circle fa-3x text-primary mb-3"></i>
                <h5>Demo Λειτουργία</h5>
                <p class="text-muted">Αυτή είναι μια demo έκδοση της εφαρμογής. Οι παραβάσεις που καταχωρούνται δεν αποθηκεύονται μόνιμα.</p>
                <p class="text-muted">Για πλήρη λειτουργικότητα, παρακαλώ εγκαταστήστε την εφαρμογή σε κανονικό περιβάλλον με Flask.</p>
                <a href="/" class="btn btn-primary"><i class="fas fa-plus me-2"></i>Δοκιμάστε τη Φόρμα Καταχώρησης</a>
            </div>
        </div>
    </div>
</body>
</html>
        """

if __name__ == '__main__':
    PORT = 9000
    print(f"🚔 Δημοτική Αστυνομία - Σύστημα Παραβάσεων")
    print(f"📡 Server ξεκινά στο http://localhost:{PORT}")
    print(f"🌐 Για πρόσβαση από άλλες συσκευές: http://0.0.0.0:{PORT}")
    
    with socketserver.TCPServer(("", PORT), ViolationHandler) as httpd:
        print(f"✅ Server ενεργός στο port {PORT}")
        httpd.serve_forever()